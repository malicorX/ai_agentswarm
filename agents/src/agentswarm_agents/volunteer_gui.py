from __future__ import annotations

import argparse
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from agentswarm_agents.client import platform_url
from agentswarm_agents.client_data_dir import client_data_dir
from agentswarm_agents.model_allowlist import default_model_id, get_model_entry, list_allowed_models
from agentswarm_agents.model_store import ensure_model_ready, model_status
from agentswarm_agents.volunteer_client import VolunteerClient, VolunteerConfig, run_headless


def _parse_capabilities(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown size"
    if value < 1024 * 1024:
        return f"{value // 1024} KiB"
    return f"{value / (1024 * 1024):.1f} GiB"


class VolunteerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AgentSwarm Volunteer")
        self.root.geometry("760x580")
        self._worker = None
        self._prepare_thread: threading.Thread | None = None
        self._build_form()
        self._append_log(f"Data directory: {client_data_dir()}")
        self._append_log("Ready. Pick a model, prepare weights if needed, then Start.")

    def _build_form(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 12, "bold")).pack(
            anchor=tk.W, pady=(0, 8)
        )

        form = ttk.Frame(frame)
        form.pack(fill=tk.X)

        self.agent_name = self._row(form, "Agent name", "volunteer-1", 0)
        self.base_url = self._row(form, "Platform URL", platform_url(), 1)
        self.owner = self._row(form, "Owner", "volunteer", 2)
        self.capabilities = self._row(form, "Capabilities", "reviewer", 3)

        model_row = ttk.Frame(form)
        model_row.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=4)
        ttk.Label(model_row, text="Model", width=16).pack(side=tk.LEFT)
        self.model_var = tk.StringVar(value=default_model_id())
        model_ids = [str(item["id"]) for item in list_allowed_models()]
        self.model_box = ttk.Combobox(
            model_row,
            textvariable=self.model_var,
            values=model_ids,
            state="readonly",
        )
        self.model_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.model_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_model_status())

        self.model_status_var = tk.StringVar(value="")
        ttk.Label(form, textvariable=self.model_status_var, wraplength=680).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, pady=(0, 4)
        )

        self.progress = ttk.Progressbar(form, mode="determinate", maximum=100)
        self.progress.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))
        self.progress.grid_remove()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=8)
        self.prepare_btn = ttk.Button(buttons, text="Prepare model", command=self.prepare_model)
        self.prepare_btn.pack(side=tk.LEFT)
        self.start_btn = ttk.Button(buttons, text="Start", command=self.start)
        self.start_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.log = scrolledtext.ScrolledText(frame, height=18, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)
        self._refresh_model_status()

    def _row(self, parent: ttk.Frame, label: str, default: str, row: int) -> tk.StringVar:
        var = tk.StringVar(value=default)
        ttk.Label(parent, text=label, width=16).grid(row=row, column=0, sticky=tk.W, pady=4)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=4)
        parent.columnconfigure(1, weight=1)
        return var

    def _append_log(self, message: str) -> None:
        def write() -> None:
            self.log.configure(state=tk.NORMAL)
            self.log.insert(tk.END, message + "\n")
            self.log.configure(state=tk.DISABLED)
            self.log.see(tk.END)

        self.root.after(0, write)

    def _set_status(self, state: str, detail: str) -> None:
        label = state.replace("_", " ").title()
        if detail:
            label = f"{label}: {detail}"

        def apply() -> None:
            self.status_var.set(label)

        self.root.after(0, apply)

    def _refresh_model_status(self) -> None:
        model_id = self.model_var.get().strip()
        entry = get_model_entry(model_id)
        if entry is None:
            self.model_status_var.set(f"{model_id}: not on allowlist")
            return
        status = model_status(model_id)
        label = str(entry.get("label", model_id))
        runtime = str(entry.get("runtime", "in-process"))
        if status["state"] == "ready" and status.get("note"):
            text = f"{label} ({runtime}) — ready, no download required"
        elif status["state"] == "ready":
            text = f"{label} ({runtime}) — ready ({_format_bytes(status.get('bytes'))})"
        elif status["state"] == "missing":
            text = (
                f"{label} ({runtime}) — not downloaded "
                f"({_format_bytes(status.get('size_bytes'))}); click Prepare model"
            )
        else:
            text = f"{label} ({runtime}) — {status['state']}"
        self.model_status_var.set(text)

    def _config(self) -> VolunteerConfig:
        capabilities = _parse_capabilities(self.capabilities.get())
        if not capabilities:
            raise ValueError("at least one capability is required")
        return VolunteerConfig(
            agent_name=self.agent_name.get().strip(),
            base_url=self.base_url.get().strip(),
            owner=self.owner.get().strip(),
            capabilities=capabilities,
            model_id=self.model_var.get().strip(),
        )

    def prepare_model(self) -> None:
        model_id = self.model_var.get().strip()
        if self._prepare_thread is not None and self._prepare_thread.is_alive():
            return

        def runner() -> None:
            try:
                self.root.after(0, lambda: self.prepare_btn.configure(state=tk.DISABLED))
                self.root.after(0, self.progress.grid)
                self.root.after(0, lambda: self.progress.configure(value=0))

                def on_progress(phase: str, done: int, total: int | None) -> None:
                    if phase == "downloading" and total:
                        pct = min(100, int(done * 100 / total))

                        def apply() -> None:
                            self.progress.configure(value=pct)

                        self.root.after(0, apply)
                    if phase == "ready":
                        self._append_log(f"Model {model_id} ready")

                ensure_model_ready(model_id, on_progress=on_progress)
            except Exception as exc:
                self._append_log(f"prepare failed: {exc}")
                self.root.after(
                    0,
                    lambda: messagebox.showerror("Model prepare failed", str(exc)),
                )
            finally:
                def cleanup() -> None:
                    self.prepare_btn.configure(state=tk.NORMAL)
                    self.progress.grid_remove()
                    self._refresh_model_status()

                self.root.after(0, cleanup)

        self._prepare_thread = threading.Thread(target=runner, name="model-prepare", daemon=True)
        self._prepare_thread.start()
        self._append_log(f"Preparing model {model_id}…")

    def start(self) -> None:
        try:
            config = self._config()
        except ValueError as exc:
            messagebox.showerror("Invalid configuration", str(exc))
            return
        if self._worker is not None and self._worker.is_alive():
            return
        stop_event = threading.Event()
        volunteer = VolunteerClient(
            config,
            on_state=self._set_status,
            on_log=self._append_log,
        )

        def runner() -> None:
            volunteer.run_until_stopped(stop_event)

        thread = threading.Thread(target=runner, name="volunteer-loop", daemon=True)
        thread.stop_event = stop_event  # type: ignore[attr-defined]
        thread.volunteer = volunteer  # type: ignore[attr-defined]
        thread.start()
        self._worker = thread
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self._append_log("Volunteer loop started.")

    def stop(self) -> None:
        if self._worker is None:
            return
        stop_event = getattr(self._worker, "stop_event", None)
        if stop_event is not None:
            stop_event.set()
        self._worker = None
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self._set_status("idle", "stopped")
        self._append_log("Stop requested.")


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentSwarm volunteer production client")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--agent-name", default="volunteer-1")
    parser.add_argument("--base-url", default=platform_url())
    parser.add_argument("--owner", default="volunteer")
    parser.add_argument("--capabilities", default="reviewer")
    parser.add_argument("--model-id", default=default_model_id())
    parser.add_argument("--loops", type=int, default=0)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Download/verify model weights then exit (docker runtime models)",
    )
    args = parser.parse_args()

    if args.prepare_only:
        ensure_model_ready(args.model_id, on_progress=lambda phase, done, total: print(phase, done, total))
        print(f"model {args.model_id} ready")
        return 0

    if args.headless:
        config = VolunteerConfig(
            agent_name=args.agent_name,
            base_url=args.base_url,
            owner=args.owner,
            capabilities=_parse_capabilities(args.capabilities),
            model_id=args.model_id,
        )
        completed = run_headless(config, loops=args.loops)
        print(f"completed {completed} assignment(s)")
        return 0

    root = tk.Tk()
    VolunteerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
