#!/usr/bin/env python3
"""
aether_events.py — append-only event stream · Layer C → Layer B 的桥

Design:
  Layer A(markdown/json) · source of truth · 不变
  Layer B(SQLite)       · index · 可重建
  Layer C(hooks)        · 反射弧 · 写 events.jsonl 并推进 Layer B

events.jsonl 是 Layer C 的"原始输出":一行一个事件 · JSON · append-only。
hook 耗时必须 < 5ms(每次工具调用都触发) · 只做 append · 不做任何决策。
indexer 稍后消费这个文件 · 物化到 SQLite。

事件 schema(稳定 · v1):
    {
      "ts": "2026-04-19T14:32:15.123Z",   # ISO 8601 · UTC · ms 精度
      "type": "tool_call|prompt|session_start|session_end|stop|coll_create|manual",
      "session_id": "sess-1776581640323",  # Cursor-provided or derived
      "tool": "edit_file",                 # tool_call only
      "payload": {...}                     # type-specific · tolerant to schema drift
    }

设计原则:
- 零依赖(stdlib only)
- 失败静默(事件丢一条比让 Cursor 崩重要得多)
- Rotation by size(>10MB 拆成 events.jsonl.1 · 保留最近 5 份)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

ROOT = Path(__file__).resolve().parent.parent                 # aether/
WORKSPACE_ROOT = ROOT.parent                                    # git root of aether itself

# Day 12 (coll-0084): path constants + resolvers moved to aether_paths.
# Imports below keep the historical names at this module's top level so
# Day 1-11 callers (`from aether_events import resolve_data_dir`) still
# work · zero breaking change.
from aether_paths import (                                      # noqa: E402
    CENTRAL_OVERLAY as DATA_DIR,
    CORE_HOME as CORE_DIR,
    CORE_SUBDIR,
    resolve_core_dir,
    resolve_overlay_dir,
)

EVENTS_PATH = DATA_DIR / "events.jsonl"

ROTATION_BYTES = 10 * 1024 * 1024                               # 10 MB
KEEP_ROTATIONS = 5


def resolve_data_dir(payload: Optional[dict] = None) -> Path:
    """DEPRECATED alias · kept for Day 1-9 callers.

    Day 10 introduces the core/overlay split · new code should call
    resolve_overlay_dir directly (explicit name) · callers reading
    identity / fields should call resolve_core_dir.
    """
    return resolve_overlay_dir(payload)


def _ensure_data_dir(target: Optional[Path] = None) -> None:
    try:
        (target or DATA_DIR).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _now_iso_utc() -> str:
    """ISO 8601 with ms precision · always UTC · Z suffix.

    Thin back-compat wrapper · delegates to aether_paths.now_iso_millis
    (fixes Day 1 race where two datetime.now() calls could disagree
    across second boundaries).
    """
    from aether_paths import now_iso_millis
    return now_iso_millis()


def _rotate_if_needed(events_path: Path) -> None:
    try:
        if not events_path.exists():
            return
        if events_path.stat().st_size < ROTATION_BYTES:
            return
        for i in range(KEEP_ROTATIONS - 1, 0, -1):
            src = events_path.with_suffix(f".jsonl.{i}")
            dst = events_path.with_suffix(f".jsonl.{i + 1}")
            if src.exists():
                try:
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)
                except OSError:
                    pass
        try:
            events_path.rename(events_path.with_suffix(".jsonl.1"))
        except OSError:
            pass
    except Exception:
        pass


def append_event(event: dict) -> bool:
    """Append one event · fail-silent · returns success bool.

    Routes to per-project data dir if event payload contains
    `workspace_roots` (set by hook handlers). Falls back to WORKSPACE_ROOT
    `.aether/` for CLI invocations.

    Caller-provided `ts` preserved (useful for backfill).
    """
    try:
        # event.payload may carry workspace_roots from the originating hook
        payload = event.get("payload") if isinstance(event, dict) else None
        target_dir = resolve_data_dir(payload if isinstance(payload, dict) else None)
        # If event itself carries workspace_roots at top level (some hook
        # paths pass it that way), honor it
        if isinstance(event, dict) and event.get("workspace_roots"):
            target_dir = resolve_data_dir({"workspace_roots": event["workspace_roots"]})
        events_path = target_dir / "events.jsonl"
        _ensure_data_dir(target_dir)
        _rotate_if_needed(events_path)
        if "ts" not in event:
            event["ts"] = _now_iso_utc()
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with open(events_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return True
    except Exception:
        return False


def read_events(
    path: Optional[Path] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    types: Optional[list[str]] = None,
    limit: Optional[int] = None,
) -> Iterator[dict]:
    """Iterate events · newest file first · filters applied streaming."""
    p = path or EVENTS_PATH
    if not p.exists():
        return
    count = 0
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if types and evt.get("type") not in types:
                    continue
                ts = evt.get("ts", "")
                if since and ts < since:
                    continue
                if until and ts > until:
                    continue
                yield evt
                count += 1
                if limit and count >= limit:
                    return
    except OSError:
        return


def count_events(types: Optional[list[str]] = None) -> int:
    """Count (may be slow on large files · use for stats only)."""
    n = 0
    for _ in read_events(types=types):
        n += 1
    return n


def tail_session(session_id: str) -> list[dict]:
    """Return all events of a given session."""
    return list(read_events(types=None)) if not session_id else [
        e for e in read_events() if e.get("session_id") == session_id
    ]


def derive_session_id(payload: dict) -> str:
    """Cursor doesn't always pass session_id · derive a stable key from
    the payload or fall back to a process-local one."""
    for k in ("session_id", "sessionId", "conversation_id", "conversationId"):
        v = payload.get(k) if isinstance(payload, dict) else None
        if v:
            return str(v)
    return f"sess-local-{os.getpid()}"


def cli_tail(n: int = 20) -> int:
    """Human-friendly tail · for debugging."""
    lines = []
    if EVENTS_PATH.exists():
        with open(EVENTS_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    tail = lines[-n:] if n < len(lines) else lines
    for ln in tail:
        try:
            e = json.loads(ln)
            short_ts = e.get("ts", "")[:19]
            t = e.get("type", "?")
            tool = e.get("tool", "")
            extra = tool and f" · {tool}" or ""
            print(f"[{short_ts}] {t:15s}{extra}")
        except Exception:
            print(ln.rstrip())
    return 0


def cli_stats() -> int:
    """Emit aggregate stats to stdout."""
    if not EVENTS_PATH.exists():
        print(f"(no events.jsonl at {EVENTS_PATH})")
        return 0
    total = 0
    by_type: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    first_ts = last_ts = ""
    for e in read_events():
        total += 1
        t = e.get("type", "?")
        by_type[t] = by_type.get(t, 0) + 1
        tool = e.get("tool")
        if tool:
            by_tool[tool] = by_tool.get(tool, 0) + 1
        ts = e.get("ts", "")
        if ts and (not first_ts or ts < first_ts):
            first_ts = ts
        if ts and ts > last_ts:
            last_ts = ts
    size = EVENTS_PATH.stat().st_size if EVENTS_PATH.exists() else 0
    print(f"events.jsonl · {size} bytes · {total} events")
    print(f"first: {first_ts}")
    print(f"last:  {last_ts}")
    print("by type:")
    for t, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {t:20s} {n:6d}")
    if by_tool:
        print("by tool (top 10):")
        for tool, n in sorted(by_tool.items(), key=lambda kv: -kv[1])[:10]:
            print(f"  {tool:20s} {n:6d}")
    return 0


def _autopilot_tick() -> None:
    """Lazy-trigger guardian if the index is stale. Silent · non-blocking."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from aether_autopilot import maybe_trigger_ingest
        maybe_trigger_ingest()
    except Exception:
        pass


def main() -> int:
    _autopilot_tick()
    import argparse
    ap = argparse.ArgumentParser(description="Aether events.jsonl helper · tail/stats/append")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_tail = sub.add_parser("tail", help="show last N events")
    p_tail.add_argument("-n", type=int, default=20)

    sub.add_parser("stats", help="aggregate stats")

    p_append = sub.add_parser("append", help="append a test event (debugging)")
    p_append.add_argument("--type", required=True)
    p_append.add_argument("--payload", default="{}")

    args = ap.parse_args()

    if args.cmd == "tail":
        return cli_tail(args.n)
    if args.cmd == "stats":
        return cli_stats()
    if args.cmd == "append":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError:
            payload = {"raw": args.payload}
        ok = append_event({"type": args.type, "payload": payload, "session_id": "manual"})
        print("ok" if ok else "failed")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
