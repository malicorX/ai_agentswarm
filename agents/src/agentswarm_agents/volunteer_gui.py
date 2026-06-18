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
from agentswarm_agents.volunteer_capabilities import (
    default_generalist_capabilities,
    format_capabilities,
    parse_capabilities_field,
)
from agentswarm_agents.volunteer_client import VolunteerClient, VolunteerConfig, run_headless
from agentswarm_agents.volunteer_work import VolunteerWorkContext, VolunteerWorkEvent


def _parse_capabilities(raw: str) -> list[str]:
    return parse_capabilities_field(raw)


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown size"
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MiB"
    return f"{value / (1024 * 1024 * 1024):.1f} GiB"


CAPABILITY_PRESETS: dict[str, str] = {
    "All roles (generalist)": format_capabilities(default_generalist_capabilities()),
    "Engineering git (full pipeline)": "coordinator,codewriter,sandbox.test,reviewer",
    "Engineering local/sandbox": "coordinator,codewriter,sandbox.build,sandbox.test,reviewer",
    "Reviewer only": "reviewer",
    "Creative + reviewer": "creative,reviewer",
}


class VolunteerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AgentSwarm Volunteer")
        self.root.geometry("900x720")
        self._worker = None
        self._prepare_thread: threading.Thread | None = None
        self._history_details: dict[str, str] = {}
        self._build_form()
        self._append_log(f"Data directory: {client_data_dir()}")
        self._append_log("Ready. Default: all roles — click Start to claim any open task.")
        self._append_log("Sandbox steps need Docker. Type 'all' in Capabilities for the same default.")

    def _apply_capability_preset(self, _event: object | None = None) -> None:
        label = self.preset_var.get()
        caps = CAPABILITY_PRESETS.get(label)
        if caps:
            self.capabilities.set(caps)

    def _build_form(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 12, "bold")).pack(
            anchor=tk.W, pady=(0, 4)
        )

        current = ttk.LabelFrame(frame, text="Current work", padding=8)
        current.pack(fill=tk.X, pady=(0, 8))
        grid = ttk.Frame(current)
        grid.pack(fill=tk.X)
        self.current_role_var = tk.StringVar(value="—")
        self.current_goal_var = tk.StringVar(value="—")
        self.current_project_var = tk.StringVar(value="—")
        self.current_task_var = tk.StringVar(value="—")
        self.current_label_var = tk.StringVar(value="—")
        self._current_field(grid, 0, "Role", self.current_role_var)
        self._current_field(grid, 1, "Goal", self.current_goal_var)
        self._current_field(grid, 2, "Project", self.current_project_var)
        self._current_field(grid, 3, "Task", self.current_task_var)
        self._current_field(grid, 4, "Work", self.current_label_var)

        form = ttk.Frame(frame)
        form.pack(fill=tk.X)

        self.agent_name = self._row(form, "Agent name", "volunteer-1", 0)
        self.base_url = self._row(form, "Platform URL", platform_url(), 1)
        self.owner = self._row(form, "Owner", "volunteer", 2)
        self.capabilities = self._row(
            form,
            "Capabilities",
            CAPABILITY_PRESETS["All roles (generalist)"],
            3,
        )

        preset_row = ttk.Frame(form)
        preset_row.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))
        ttk.Label(preset_row, text="Preset", width=16).pack(side=tk.LEFT)
        self.preset_var = tk.StringVar(value="All roles (generalist)")
        preset_box = ttk.Combobox(
            preset_row,
            textvariable=self.preset_var,
            values=list(CAPABILITY_PRESETS.keys()),
            state="readonly",
        )
        preset_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        preset_box.bind("<<ComboboxSelected>>", self._apply_capability_preset)

        model_row = ttk.Frame(form)
        model_row.grid(row=5, column=0, columnspan=2, sticky=tk.EW, pady=4)
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
            row=6, column=0, columnspan=2, sticky=tk.W, pady=(0, 4)
        )

        self.progress = ttk.Progressbar(form, mode="determinate", maximum=100)
        self.progress.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))
        self.progress.grid_remove()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=8)
        self.prepare_btn = ttk.Button(buttons, text="Prepare model", command=self.prepare_model)
        self.prepare_btn.pack(side=tk.LEFT)
        self.start_btn = ttk.Button(buttons, text="Start", command=self.start)
        self.start_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        panes = ttk.Panedwindow(frame, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True)

        history_frame = ttk.LabelFrame(panes, text="Work history", padding=4)
        panes.add(history_frame, weight=2)
        columns = ("time", "role", "goal", "project", "status", "summary")
        self.history_tree = ttk.Treeview(
            history_frame,
            columns=columns,
            show="headings",
            height=7,
        )
        headings = {
            "time": ("Time", 72),
            "role": ("Role", 88),
            "goal": ("Goal", 120),
            "project": ("Project", 72),
            "status": ("Status", 64),
            "summary": ("Summary", 280),
        }
        for col, (label, width) in headings.items():
            self.history_tree.heading(col, text=label)
            self.history_tree.column(col, width=width, anchor=tk.W)
        history_scroll = ttk.Scrollbar(
            history_frame, orient=tk.VERTICAL, command=self.history_tree.yview
        )
        self.history_tree.configure(yscrollcommand=history_scroll.set)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.bind("<<TreeviewSelect>>", self._show_history_detail)

        self.history_detail = scrolledtext.ScrolledText(
            history_frame, height=4, state=tk.DISABLED, wrap=tk.WORD
        )
        self.history_detail.pack(fill=tk.X, pady=(4, 0))

        log_frame = ttk.LabelFrame(panes, text="Log", padding=4)
        panes.add(log_frame, weight=3)
        self.log = scrolledtext.ScrolledText(log_frame, height=12, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)
        self._refresh_model_status()

    def _current_field(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar) -> None:
        ttk.Label(parent, text=f"{label}:", width=10).grid(row=row, column=0, sticky=tk.W, pady=1)
        ttk.Label(parent, textvariable=var, wraplength=720).grid(
            row=row, column=1, sticky=tk.W, pady=1
        )
        parent.columnconfigure(1, weight=1)

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

    def _apply_current_work(self, context: VolunteerWorkContext | None) -> None:
        if context is None:
            self.current_role_var.set("—")
            self.current_goal_var.set("—")
            self.current_project_var.set("—")
            self.current_task_var.set("—")
            self.current_label_var.set("—")
            return
        self.current_role_var.set(f"{context.role} ({context.task_type})")
        self.current_goal_var.set(context.goal_display)
        self.current_project_var.set(context.project_display)
        self.current_task_var.set(context.task_id)
        self.current_label_var.set(context.label)

    def _set_current_work(self, context: VolunteerWorkContext | None) -> None:
        self.root.after(0, lambda: self._apply_current_work(context))

    def _format_event_time(self, event: VolunteerWorkEvent) -> str:
        stamp = event.finished_at or event.started_at
        return stamp.astimezone().strftime("%H:%M:%S")

    def _on_work_event(self, event: VolunteerWorkEvent) -> None:
        def apply() -> None:
            ctx = event.context
            if event.kind == "started":
                self._apply_current_work(ctx)
                self.history_tree.insert(
                    "",
                    0,
                    iid=ctx.task_id,
                    values=(
                        self._format_event_time(event),
                        ctx.role,
                        ctx.goal_display,
                        ctx.project_display,
                        "running",
                        ctx.label,
                    ),
                )
                return
            status = "ok" if event.status == "ok" else "error"
            summary = event.summary or status
            if self.history_tree.exists(ctx.task_id):
                self.history_tree.item(
                    ctx.task_id,
                    values=(
                        self._format_event_time(event),
                        ctx.role,
                        ctx.goal_display,
                        ctx.project_display,
                        status,
                        summary,
                    ),
                )
            else:
                self.history_tree.insert(
                    "",
                    0,
                    iid=ctx.task_id,
                    values=(
                        self._format_event_time(event),
                        ctx.role,
                        ctx.goal_display,
                        ctx.project_display,
                        status,
                        summary,
                    ),
                )
            detail_parts = [f"task: {ctx.task_id}", f"role: {ctx.role} ({ctx.task_type})"]
            if ctx.goal_id:
                detail_parts.append(f"goal: {ctx.goal_id}")
            if ctx.project_id:
                detail_parts.append(f"project: {ctx.project_id}")
            if event.submission_id:
                detail_parts.append(f"submission: {event.submission_id}")
            detail_parts.append(f"summary: {summary}")
            if event.detail:
                detail_parts.append("")
                detail_parts.append(event.detail)
            self._history_details[ctx.task_id] = "\n".join(detail_parts)
            self._apply_current_work(None)

        self.root.after(0, apply)

    def _show_history_detail(self, _event: object | None = None) -> None:
        selected = self.history_tree.selection()
        if not selected:
            return
        task_id = selected[0]
        detail = self._history_details.get(task_id, "")
        if not detail:
            values = self.history_tree.item(task_id, "values")
            if values:
                detail = " · ".join(str(part) for part in values if part)
        self.history_detail.configure(state=tk.NORMAL)
        self.history_detail.delete("1.0", tk.END)
        self.history_detail.insert(tk.END, detail or "(no detail recorded)")
        self.history_detail.configure(state=tk.DISABLED)

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
            on_work_event=self._on_work_event,
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
        self._append_log(f"capabilities: {', '.join(config.capabilities)}")

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
        self._set_current_work(None)
        self._append_log("Stop requested.")


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentSwarm volunteer production client")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--agent-name", default="volunteer-1")
    parser.add_argument("--base-url", default=platform_url())
    parser.add_argument("--owner", default="volunteer")
    parser.add_argument("--capabilities", default=format_capabilities(default_generalist_capabilities()))
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
