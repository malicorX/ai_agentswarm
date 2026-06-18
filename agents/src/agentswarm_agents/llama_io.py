"""Keep llama.cpp noise off stdout/stderr; worker protocol stays JSON-only."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from typing import Iterator


def llama_logging_enabled() -> bool:
    raw = os.environ.get("AGENTSWARM_LLAMA_LOG", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@contextlib.contextmanager
def suppress_native_stderr() -> Iterator[None]:
    """Redirect fd 2 so llama.cpp C logs do not pollute worker stderr."""
    if llama_logging_enabled():
        yield
        return
    stderr_fd = sys.stderr.fileno()
    saved_fd = os.dup(stderr_fd)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, stderr_fd)
        yield
    finally:
        os.dup2(saved_fd, stderr_fd)
        os.close(saved_fd)
        os.close(devnull_fd)


def install_llama_log_sink() -> None:
    """No-op log callback for llama-cpp-python (when available)."""
    if llama_logging_enabled():
        return
    try:
        import ctypes
        from llama_cpp import llama_log_set
    except ImportError:
        return

    def _callback(level: int, text: bytes, user_data: object) -> None:
        del level, text, user_data

    log_fn = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)(
        _callback
    )
    llama_log_set(log_fn, ctypes.c_void_p())


def parse_worker_container_failure(
    *,
    stdout: str,
    stderr: str,
    exit_code: int,
) -> str:
    """Return a short operator-facing error without llama preamble noise."""
    for blob in (stderr, stdout):
        for line in reversed(blob.splitlines()):
            cleaned = line.strip()
            if not cleaned.startswith("{"):
                continue
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                error = parsed.get("error")
                if isinstance(error, str) and error.strip():
                    return error.strip()
    useful = _filter_llama_noise(stderr) or _filter_llama_noise(stdout)
    if useful:
        return useful[-600:]
    return f"worker container exited with code {exit_code}"


def _filter_llama_noise(text: str) -> str:
    if not text.strip():
        return ""
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("llama_") or "n_ctx_per_seq" in lower:
            continue
        if stripped.startswith("ggml_") or "graph splits" in lower:
            continue
        kept.append(stripped)
    return "\n".join(kept)
