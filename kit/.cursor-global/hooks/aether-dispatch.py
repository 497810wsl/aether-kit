#!/usr/bin/env python3
"""
aether-dispatch.py — USER-LEVEL Cursor hook · cross-platform

Installed once to ~/.cursor/hooks/. Fires for EVERY new Cursor session
on any workspace. Acts as a dispatcher:

    workspace has aether/bin/aether_hook.py?
        YES  → exec that project's hook · use its briefing
        NO   → return {} · zero effect on non-Aether projects

This is how "PROTOCOL 0" becomes opt-in per-project without
requiring per-project hook config. Drop an `aether/` folder into any
repo · global dispatcher picks it up · session gets briefing. Delete
the folder · global dispatcher silently skips.

Hook spec:
- Event: sessionStart
- Input (stdin JSON): { "workspace_roots": [...], "session_id": ... }
- Output (stdout JSON): whatever the per-project hook returned, or
  '{}' for non-Aether projects.
- Fail-open at every layer · hook failures never block session.

Cross-platform notes:
- Python 3.6+ on Windows / macOS / Linux.
- sys.stdin.buffer.read() used to avoid Windows cp936 codepage
  corruption (see Anthropic GitHub #48009 for the broader context).
- Silent on non-Aether projects · prints nothing, writes nothing.

Distributed by: https://github.com/497810wsl/aether-kit
License: MIT
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def read_stdin_json() -> dict:
    """Parse Cursor's sessionStart payload. Returns {} on any failure."""
    try:
        if sys.stdin.isatty():
            return {}
    except Exception:
        pass
    try:
        raw_bytes = sys.stdin.buffer.read()
    except Exception:
        try:
            raw = sys.stdin.read()
            raw_bytes = raw.encode("utf-8") if raw else b""
        except Exception:
            return {}
    if not raw_bytes:
        return {}
    try:
        raw = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def reply_pass_through() -> None:
    """Silent no-op · session proceeds without injected context."""
    sys.stdout.write("{}")
    sys.stdout.flush()
    sys.exit(0)


def pick_workspace_root(payload: dict) -> Path | None:
    """Extract the first workspace root from Cursor's payload.

    Cursor sends paths like "/c:/Users/foo/桌面/..." on Windows · need
    to strip leading slash and normalise. Other OSes get native paths.
    """
    roots = payload.get("workspace_roots") or []
    if not roots:
        return None
    raw = roots[0]
    if not isinstance(raw, str):
        return None
    # Windows · Cursor sends "/c:/Users/..." · strip the leading slash.
    if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        raw = raw[1:]
    try:
        return Path(raw).resolve()
    except Exception:
        return None


def find_project_hook(workspace: Path) -> Path | None:
    """Does this workspace opt-in to Aether? Look for the canonical marker
    file: aether/bin/aether_hook.py. If present · return its absolute path."""
    candidate = workspace / "aether" / "bin" / "aether_hook.py"
    try:
        if candidate.is_file():
            return candidate
    except OSError:
        pass
    return None


def main() -> int:
    # Accept but ignore --event=<name> and similar · we're only called on
    # sessionStart so we don't need to dispatch by event type ourselves.
    # (hooks.json command string can include flags · we don't parse them.)
    payload = read_stdin_json()

    workspace = pick_workspace_root(payload)
    if workspace is None:
        reply_pass_through()

    project_hook = find_project_hook(workspace)
    if project_hook is None:
        reply_pass_through()

    # Exec the project's own hook · feed it the SAME payload we got.
    # Use the same Python interpreter so we don't need the user's PATH
    # to resolve python again.
    try:
        result = subprocess.run(
            [sys.executable, str(project_hook), "--event", "sessionStart"],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            timeout=25,
            cwd=str(workspace),
        )
    except Exception:
        reply_pass_through()

    if result.returncode != 0:
        reply_pass_through()

    # Forward the project hook's JSON response verbatim (bytes · avoids
    # re-encoding · preserves any nested unicode).
    try:
        sys.stdout.buffer.write(result.stdout)
        sys.stdout.flush()
    except Exception:
        reply_pass_through()
    sys.exit(0)


if __name__ == "__main__":
    main()
