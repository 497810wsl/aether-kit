#!/usr/bin/env python3
"""
aether_autopilot.py — 跨平台懒触发引擎 · 零 OS 依赖

设计原则(Owner 明确要求):
  · 不依赖 Windows 任务计划程序 / systemd / launchd / cron 任何 OS 定时器
  · 不启动常驻 daemon 进程
  · 纯 Python + 文件状态 · Windows/Mac/Linux 表现完全一致
  · 任何 aether CLI 被调用都顺手推进一次反射弧 · 调用越多、系统越新鲜

工作方式:
  1. 每个常用 CLI 启动时 import 这个模块并调用 maybe_trigger()
  2. maybe_trigger() 读 .aether/guardian-state.json 看 indexer_ingest.last_run
  3. 如果距上次 >= min_gap_seconds, fire-and-forget 一个子进程跑 guardian --once
  4. 立刻返回 · 绝不阻塞用户命令 · 绝不抛异常

等价于一个"用户驱动的 cron":
  · 用户每次跑 aether_query / aether_events / aether_selfcheck 等 = 一次免费推进
  · 即使用户一整天不开 Cursor · 只要跑过一次 CLI · 系统就是新鲜的
  · 零 OS 依赖 · 零进程守护 · 零安装步骤

这就是 Memory v2 的"心跳" · 而心跳的来源是 Owner 自己的手指。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aether_paths import (
    CENTRAL_OVERLAY,
    CENTRAL_ROOT,
    activate_overlay_for_cli,
    add_path_arg,
    resolve_active_overlay,
)

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = CENTRAL_ROOT                   # back-compat alias
GUARDIAN_SCRIPT = ROOT / "bin" / "aether_guardian.py"

# Day 13 · overlay-aware · PATH-RESOLUTION-SPEC §3.1
# The autopilot's "lazy cron" now fires a guardian --once for the ACTIVE
# overlay, not always for central. Default module-level paths point at
# central; maybe_trigger_ingest(cwd=...) resolves per call.
DEFAULT_MIN_GAP_SECONDS = 300          # 5 分钟
AUTOPILOT_OWN_GAP_SECONDS = 60         # autopilot 自己节流 · 1 分钟内不重复触发


def _read_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _seconds_since(iso_ts: str) -> float:
    """Seconds since iso_ts · returns inf if parse fails."""
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return float("inf")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _launch_detached(cmd: list[str], cwd: Optional[Path] = None) -> None:
    """Fire-and-forget · never blocks caller · swallows all errors.

    On Windows we use CREATE_NO_WINDOW + DETACHED_PROCESS so the child
    doesn't inherit the parent's console (user sees nothing). On POSIX
    we use start_new_session. Either way · parent exits immediately
    after spawning.

    Day 13 · `cwd` is now parameterized · lets the child inherit a
    guest-project cwd so its own activate_overlay_for_cli() discovers
    the right overlay without needing an explicit --path flag.
    """
    try:
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            CREATE_NO_WINDOW = 0x08000000
            DETACHED_PROCESS = 0x00000008
            kwargs["creationflags"] = CREATE_NO_WINDOW | DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, cwd=str(cwd or WORKSPACE_ROOT), **kwargs)
    except Exception:
        pass


def _resolve_overlay(cwd: Optional[str | Path]) -> Path:
    """Resolve the overlay for the given cwd · central fallback."""
    try:
        overlay, _ = resolve_active_overlay(cwd=cwd) if cwd else resolve_active_overlay()
        return overlay
    except Exception:
        return CENTRAL_OVERLAY


def maybe_trigger_ingest(
    min_gap_seconds: int = DEFAULT_MIN_GAP_SECONDS,
    *,
    force: bool = False,
    quiet: bool = True,
    cwd: Optional[str | Path] = None,
) -> bool:
    """Maybe launch a background guardian --once run for the ACTIVE overlay.

    Returns True if we fired a subprocess · False if we skipped (not
    needed yet or throttled). Never raises.

    Args:
      min_gap_seconds: consider the system "stale" if indexer_ingest
        hasn't run in this many seconds. Default 300 (5 min).
      force: ignore the gap check and fire anyway.
      quiet: if False · print a one-line reason to stderr when firing.
      cwd:   resolve the active overlay from this directory (default Path.cwd()).
             Day 13 · per-overlay heartbeat: each CLI invocation advances
             the overlay it was invoked from, not always central.

    Strategy:
      1. If guardian-state.json missing · system not initialized · skip
         (don't auto-initialize · that's an explicit user decision)
      2. If indexer_ingest.last_run < min_gap · skip (system fresh)
      3. If autopilot itself fired within AUTOPILOT_OWN_GAP · skip
         (avoid stampede when user runs 5 CLIs back-to-back)
      4. Otherwise · launch detached subprocess · record autopilot trigger
    """
    try:
        if not force and not GUARDIAN_SCRIPT.exists():
            return False

        overlay = _resolve_overlay(cwd)
        if not overlay.exists():
            return False

        guardian_state_path = overlay / "guardian-state.json"
        autopilot_state_path = overlay / "autopilot-state.json"

        # Throttle: autopilot's own minimum gap (per-overlay counter)
        autopilot_state = _read_json(autopilot_state_path)
        own_last = autopilot_state.get("last_trigger", "")
        if not force and own_last and _seconds_since(own_last) < AUTOPILOT_OWN_GAP_SECONDS:
            return False

        # Check guardian staleness (per-overlay counter)
        guardian_state = _read_json(guardian_state_path)
        last_run = guardian_state.get("last_run", {}).get("indexer_ingest", "")
        stale_seconds = _seconds_since(last_run) if last_run else float("inf")
        if not force and stale_seconds < min_gap_seconds:
            return False

        # Fire · detached · never blocks · pass --path so the child
        # guardian operates on the same overlay we just inspected.
        cmd = [
            sys.executable, str(GUARDIAN_SCRIPT),
            "--once", "--force", "indexer_ingest",
            "--path", str(overlay.parent),
        ]
        _launch_detached(cmd, cwd=overlay.parent)

        autopilot_state["last_trigger"] = _now_iso()
        autopilot_state["last_stale_seconds"] = int(stale_seconds) if stale_seconds != float("inf") else -1
        autopilot_state["last_overlay"] = str(overlay)
        _write_json(autopilot_state_path, autopilot_state)

        if not quiet:
            try:
                print(
                    f"[autopilot] fired guardian --once (overlay={overlay.parent.name} "
                    f"· stale {int(stale_seconds)}s)",
                    file=sys.stderr,
                )
            except Exception:
                pass
        return True
    except Exception:
        return False


def status(cwd: Optional[str | Path] = None) -> dict:
    """Return autopilot + guardian staleness snapshot for the active overlay."""
    overlay = _resolve_overlay(cwd)
    guardian_state_path = overlay / "guardian-state.json"
    autopilot_state_path = overlay / "autopilot-state.json"
    guardian_state = _read_json(guardian_state_path)
    autopilot_state = _read_json(autopilot_state_path)
    last_ingest = guardian_state.get("last_run", {}).get("indexer_ingest", "")
    last_trigger = autopilot_state.get("last_trigger", "")
    return {
        "overlay": str(overlay),
        "indexer_last_run": last_ingest or None,
        "indexer_stale_seconds": int(_seconds_since(last_ingest)) if last_ingest else None,
        "autopilot_last_trigger": last_trigger or None,
        "autopilot_throttle_remaining_seconds": max(
            0,
            AUTOPILOT_OWN_GAP_SECONDS - int(_seconds_since(last_trigger)),
        ) if last_trigger else 0,
        "default_min_gap_seconds": DEFAULT_MIN_GAP_SECONDS,
    }


def main() -> int:
    """CLI for manual inspection / force-trigger.

    Usage:
      python bin/aether_autopilot.py status        # show state (active overlay)
      python bin/aether_autopilot.py trigger       # force trigger
      python bin/aether_autopilot.py check         # check (may fire)
      python bin/aether_autopilot.py status --path D:\\proj  # specific overlay
    """
    import argparse
    ap = argparse.ArgumentParser(description="Aether autopilot · lazy trigger engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="show autopilot + guardian state")
    add_path_arg(s)
    t = sub.add_parser("trigger", help="force an immediate guardian --once ingest")
    add_path_arg(t)
    c = sub.add_parser("check", help="check staleness and maybe fire (normal usage)")
    c.add_argument("--min-gap", type=int, default=DEFAULT_MIN_GAP_SECONDS)
    add_path_arg(c)
    args = ap.parse_args()

    # Resolve cwd for commands — --path always beats cwd discovery.
    resolve_cwd = getattr(args, "path", None)

    if args.cmd == "status":
        # activate banner to stderr so user sees which overlay we inspect
        activate_overlay_for_cli(args, announce=True)
        print(json.dumps(status(cwd=resolve_cwd), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "trigger":
        activate_overlay_for_cli(args, announce=True)
        fired = maybe_trigger_ingest(force=True, quiet=False, cwd=resolve_cwd)
        print("fired" if fired else "skipped")
        return 0
    if args.cmd == "check":
        activate_overlay_for_cli(args, announce=True)
        fired = maybe_trigger_ingest(
            min_gap_seconds=args.min_gap, quiet=False, cwd=resolve_cwd,
        )
        print("fired" if fired else "skipped(fresh)")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
