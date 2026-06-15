from __future__ import annotations

import argparse
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from agentswarm_agents.client import platform_url
from agentswarm_agents.model_allowlist import default_model_id, list_allowed_models
from agentswarm_agents.volunteer_client import VolunteerClient, VolunteerConfig, run_headless


def _parse_capabilities(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


class VolunteerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AgentSwarm Volunteer")
        self.root.geometry("720x520")
        self._worker = None
        self._build_form()
        self._append_log("Ready. Configure and press Start.")

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

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=8)
        self.start_btn = ttk.Button(buttons, text="Start", command=self.start)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.log = scrolledtext.ScrolledText(frame, height=18, state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True)

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

    def start(self) -> None:
        try:
            config = self._config()
        except ValueError as exc:
            messagebox.showerror("Invalid configuration", str(exc))
            return
        if self._worker is not None and self._worker.is_alive():
            return
        import threading

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
    args = parser.parse_args()

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
