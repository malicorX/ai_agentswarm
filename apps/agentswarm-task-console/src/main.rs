// Release builds: no extra console window (UI is the native WebView shell, not a browser).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use tao::event::{Event, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoopBuilder};
use tao::window::WindowBuilder;
use wry::WebViewBuilder;

const DEFAULT_PORT: u16 = 8765;
const PORT_SCAN_MAX: u16 = 20;

struct ServerProcess {
    child: Child,
}

impl Drop for ServerProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn main() {
    if let Err(err) = run() {
        show_fatal_error(&format!("AgentSwarm Task Console failed:\n{err}"));
        std::process::exit(1);
    }
}

#[cfg(all(windows, not(debug_assertions)))]
fn show_fatal_error(message: &str) {
    use std::ffi::OsStr;
    use std::iter::once;
    use std::os::windows::ffi::OsStrExt;

    extern "system" {
        fn MessageBoxW(hwnd: *mut std::ffi::c_void, text: *const u16, caption: *const u16, utype: u32) -> i32;
    }

    fn wide(value: &str) -> Vec<u16> {
        OsStr::new(value).encode_wide().chain(once(0)).collect()
    }

    let text = wide(message);
    let caption = wide("AgentSwarm Task Console");
    unsafe {
        MessageBoxW(
            std::ptr::null_mut(),
            text.as_ptr(),
            caption.as_ptr(),
            0x00000010, // MB_ICONERROR
        );
    }
}

#[cfg(not(all(windows, not(debug_assertions))))]
fn show_fatal_error(message: &str) {
    eprintln!("{message}");
}

fn is_local_console_url(url: &str) -> bool {
    url.starts_with("http://127.0.0.1:")
        || url.starts_with("http://localhost:")
        || url.starts_with("https://127.0.0.1:")
        || url.starts_with("https://localhost:")
}

fn run() -> Result<(), String> {
    let repo_root = resolve_repo_root()?;
    std::env::set_current_dir(&repo_root).map_err(|e| format!("set repo cwd: {e}"))?;
    std::env::set_var("AGENTSWARM_REPO_ROOT", &repo_root);
    let python = resolve_python(&repo_root)?;
    let port = pick_port(DEFAULT_PORT)?;
    let server = start_server(&repo_root, &python, port)?;
    #[cfg(debug_assertions)]
    eprintln!("Task console backend on http://127.0.0.1:{port}/");
    wait_for_server(port)?;

    let url = format!("http://127.0.0.1:{port}/");
    let server = Arc::new(Mutex::new(server));

    let event_loop = EventLoopBuilder::new().build();
    let window = WindowBuilder::new()
        .with_title("AgentSwarm Task Console")
        .with_inner_size(tao::dpi::LogicalSize::new(1280.0, 860.0))
        .build(&event_loop)
        .map_err(|e| format!("create window: {e}"))?;

    let _webview = WebViewBuilder::new()
        .with_url(&url)
        .with_navigation_handler(|nav_url| is_local_console_url(&nav_url))
        .with_new_window_req_handler(|_nav_url| false)
        .build(&window)
        .map_err(|e| format!("create webview: {e}"))?;

    let server_for_loop = Arc::clone(&server);
    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;
        if let Event::WindowEvent {
            event: WindowEvent::CloseRequested,
            ..
        } = event
        {
            if let Ok(mut guard) = server_for_loop.lock() {
                let _ = guard.child.kill();
                let _ = guard.child.wait();
            }
            *control_flow = ControlFlow::Exit;
        }
    });
}

fn resolve_repo_root() -> Result<PathBuf, String> {
    if let Ok(root) = env::var("AGENTSWARM_REPO_ROOT") {
        let path = PathBuf::from(root);
        if is_repo_root(&path) {
            return Ok(path);
        }
        return Err(format!(
            "AGENTSWARM_REPO_ROOT is set but invalid: {}",
            path.display()
        ));
    }

    if let Ok(cwd) = env::current_dir() {
        if let Some(found) = find_repo_root(&cwd) {
            return Ok(found);
        }
    }

    if let Ok(exe) = env::current_exe() {
        let mut dir = exe.parent().map(Path::to_path_buf);
        for _ in 0..8 {
            let Some(path) = dir else { break };
            if is_repo_root(&path) {
                return Ok(path.to_path_buf());
            }
            dir = path.parent().map(Path::to_path_buf);
        }
    }

    Err(
        "Could not find AgentSwarm repo root (need platform/, agents/, tools/task_console/).\n\
         Run dist\\TaskConsole.cmd from the repo, or set AGENTSWARM_REPO_ROOT."
            .to_string(),
    )
}

fn is_repo_root(path: &Path) -> bool {
    path.join("platform").is_dir()
        && path.join("agents").is_dir()
        && path.join("tools/task_console/server.py").is_file()
}

fn find_repo_root(start: &Path) -> Option<PathBuf> {
    let mut current = Some(start);
    for _ in 0..10 {
        let path = current?;
        if is_repo_root(path) {
            return Some(path.to_path_buf());
        }
        current = path.parent();
    }
    None
}

fn resolve_python(repo_root: &Path) -> Result<PathBuf, String> {
    let venv_python = repo_root
        .join(".venv")
        .join("Scripts")
        .join("python.exe");
    if venv_python.is_file() {
        return Ok(venv_python);
    }
    let venv_unix = repo_root.join(".venv").join("bin").join("python");
    if venv_unix.is_file() {
        return Ok(venv_unix);
    }
    if Command::new("python")
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
    {
        return Ok(PathBuf::from("python"));
    }
    Err(format!(
        "Python not found. From the repo root run: python -m venv .venv && .venv\\Scripts\\pip install -e platform -e agents"
    ))
}

fn pick_port(start: u16) -> Result<u16, String> {
    for offset in 0..PORT_SCAN_MAX {
        let port = start + offset;
        if port_is_free(port) {
            return Ok(port);
        }
    }
    Err(format!(
        "No free port in range {start}..{}",
        start + PORT_SCAN_MAX - 1
    ))
}

fn port_is_free(port: u16) -> bool {
    std::net::TcpListener::bind(("127.0.0.1", port)).is_ok()
}

#[cfg(windows)]
fn hide_console_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x08000000;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn hide_console_window(_command: &mut Command) {}

fn start_server(repo_root: &Path, python: &Path, port: u16) -> Result<ServerProcess, String> {
    let mut command = Command::new(python);
    command
        .args(["-m", "tools.task_console.server"])
        .current_dir(repo_root)
        .env("AGENTSWARM_REPO_ROOT", repo_root)
        .env("AGENTSWARM_TASK_CONSOLE_PORT", port.to_string());
    for key in [
        "AGENTSWARM_BOOTSTRAP_TOKEN",
        "AGENTSWARM_OWNER_TOKEN",
        "AGENTSWARM_STAGING_API_URL",
        "AGENTSWARM_PLATFORM_URL",
        "AGENTSWARM_ASSIGNMENT_SECRET",
    ] {
        if let Ok(value) = env::var(key) {
            if !value.trim().is_empty() {
                command.env(key, value);
            }
        }
    }
    command.stdout(Stdio::null()).stderr(Stdio::null());
    hide_console_window(&mut command);

    let child = command
        .spawn()
        .map_err(|e| format!("start python server: {e}"))?;

    Ok(ServerProcess { child })
}

fn wait_for_server(port: u16) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("http client: {e}"))?;
    let url = format!("http://127.0.0.1:{port}/api/config");
    let deadline = Instant::now() + Duration::from_secs(45);
    while Instant::now() < deadline {
        if let Ok(response) = client.get(&url).send() {
            if response.status().is_success() {
                return Ok(());
            }
        }
        thread::sleep(Duration::from_millis(250));
    }
    Err(format!(
        "Task console server did not become ready on port {port} within 45s"
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repo_root_detection() {
        let root = env::current_dir().expect("cwd");
        if is_repo_root(&root) {
            assert!(find_repo_root(&root).is_some());
        }
    }
}
