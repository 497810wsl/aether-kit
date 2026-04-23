#!/usr/bin/env python3
"""
aether_tasks.py — 任务账本(Layer A · jsonl)

把"P0/P1 散落在 markdown handover"升级为"机器可查的账本"。
每条任务一行 jsonl · 永不删除(close 是状态变更 · 不是删除)。

设计动机(coll-0071 · Day 8):
  · selfcheck 100/100 只查文件存在 · 不查"决策是否落地"
  · day-N-handover.md 中的 P0/P1/P2 是字符串 · grep 才能找到
  · 没有"未完成 P0 已经超 3 天"这样的红色信号
  · AI 写"已完成 P0.3"无证据 · 谁都看不出在撒谎

数据契约(stable · 加字段不 break):
  {
    "id":         "task-0001",          # 自增
    "created_at": "2026-04-19T10:30Z",  # ISO UTC
    "day":        8,                    # 30-day plan day
    "priority":   "P0" | "P1" | "P2" | "P3",
    "title":      "短句标题",
    "detail":     "可选 · 详细描述",
    "proof_kind": "coll" | "commit" | "file" | "url" | null,
                                        # 关闭时需要什么样的证据
    "status":     "open" | "done" | "dropped" | "deferred",
    "closed_at":  "2026-04-19T11:00Z" | null,
    "proof_ref":  "coll-0071" | "abc1234" | null,
    "owner":      "ai" | "owner",       # 谁负责执行
    "tags":       ["memory-v2", "reflex"],
  }

CLI:
  aether_tasks.py add P0 "fix critic --json" --day 8 --proof-kind coll --tags memory-v2
  aether_tasks.py list                        # all open
  aether_tasks.py list --status all
  aether_tasks.py list --priority P0 --json
  aether_tasks.py close task-0003 --proof coll-0071
  aether_tasks.py defer task-0007 --to-day 10
  aether_tasks.py drop task-0009 --reason "obsolete"
  aether_tasks.py audit                        # show stale + json summary
  aether_tasks.py audit --json                 # for selfcheck L7

Stale rules (audit):
  · open P0 > 3 days  → red (penalty: -10 health)
  · open P1 > 7 days  → orange (penalty: -5 health)
  · open P2 > 14 days → yellow (penalty: -2 health)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Day 11 · overlay-aware data dir resolution (fixes B0-1 of coll-0083).
# Before Day 11 these were hard-coded to CENTRAL's .aether · which meant
# `aether tasks add` always polluted Aether-dev's ledger regardless of
# the user's cwd. Now resolved per-invocation in main().
from aether_paths import resolve_active_overlay, CENTRAL_ROOT

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = CENTRAL_ROOT                    # kept for back-compat; same value

# Module-level paths · set to central default for old in-process importers.
# main() reassigns these based on --path / env / cwd-walk BEFORE any
# read/write happens. _read_all / _write_all deliberately don't capture
# these at import time · they reference the module globals at call time.
DATA_DIR = WORKSPACE_ROOT / ".aether"
TASKS_PATH = DATA_DIR / "tasks.jsonl"

PRIORITY_VALUES = ("P0", "P1", "P2", "P3")
STATUS_VALUES = ("open", "done", "dropped", "deferred")
PROOF_KIND_VALUES = ("coll", "commit", "file", "url", None)

STALE_THRESHOLDS = {
    "P0": (3, 10),
    "P1": (7, 5),
    "P2": (14, 2),
    "P3": (30, 1),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_all() -> list[dict]:
    if not TASKS_PATH.exists():
        return []
    out: list[dict] = []
    try:
        with open(TASKS_PATH, "r", encoding="utf-8", errors="replace") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def _write_all(tasks: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TASKS_PATH.with_suffix(".jsonl.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        tmp.replace(TASKS_PATH)
    except OSError as e:
        print(f"write tasks.jsonl failed: {e}", file=sys.stderr)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _next_id(tasks: list[dict]) -> str:
    n = 0
    for t in tasks:
        m = re.match(r"task-(\d+)", t.get("id", ""))
        if m:
            n = max(n, int(m.group(1)))
    return f"task-{n + 1:04d}"


def _seconds_since(iso_ts: str) -> float:
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return 0.0


def cmd_add(args: argparse.Namespace) -> int:
    if args.priority not in PRIORITY_VALUES:
        print(f"priority must be one of {PRIORITY_VALUES}", file=sys.stderr)
        return 2
    tasks = _read_all()
    new = {
        "id": _next_id(tasks),
        "created_at": now_iso(),
        "day": args.day,
        "priority": args.priority,
        "title": args.title.strip(),
        "detail": (args.detail or "").strip() or None,
        "proof_kind": args.proof_kind,
        "status": "open",
        "closed_at": None,
        "proof_ref": None,
        "owner": args.owner,
        "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
    }
    tasks.append(new)
    _write_all(tasks)
    print(f"+ {new['id']}  [{new['priority']}] {new['title']}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    tasks = _read_all()
    found = False
    for t in tasks:
        if t.get("id") == args.id:
            t["status"] = "done"
            t["closed_at"] = now_iso()
            t["proof_ref"] = args.proof
            found = True
            break
    if not found:
        print(f"task not found: {args.id}", file=sys.stderr)
        return 1
    _write_all(tasks)
    print(f"✓ {args.id} closed · proof={args.proof}")
    return 0


def cmd_defer(args: argparse.Namespace) -> int:
    tasks = _read_all()
    found = False
    for t in tasks:
        if t.get("id") == args.id:
            t["status"] = "deferred"
            t["day"] = args.to_day
            t["closed_at"] = now_iso()
            found = True
            break
    if not found:
        print(f"task not found: {args.id}", file=sys.stderr)
        return 1
    _write_all(tasks)
    print(f"→ {args.id} deferred to Day {args.to_day}")
    return 0


def cmd_drop(args: argparse.Namespace) -> int:
    tasks = _read_all()
    found = False
    for t in tasks:
        if t.get("id") == args.id:
            t["status"] = "dropped"
            t["closed_at"] = now_iso()
            t["proof_ref"] = f"reason: {args.reason}" if args.reason else None
            found = True
            break
    if not found:
        print(f"task not found: {args.id}", file=sys.stderr)
        return 1
    _write_all(tasks)
    print(f"× {args.id} dropped · {args.reason or '(no reason)'}")
    return 0


def cmd_reopen(args: argparse.Namespace) -> int:
    tasks = _read_all()
    found = False
    for t in tasks:
        if t.get("id") == args.id:
            t["status"] = "open"
            t["closed_at"] = None
            t["proof_ref"] = None
            found = True
            break
    if not found:
        print(f"task not found: {args.id}", file=sys.stderr)
        return 1
    _write_all(tasks)
    print(f"↺ {args.id} reopened")
    return 0


def _filter_tasks(tasks: list[dict], status: str, priority: Optional[str],
                  day: Optional[int]) -> list[dict]:
    out = tasks
    if status != "all":
        out = [t for t in out if t.get("status") == status]
    if priority:
        out = [t for t in out if t.get("priority") == priority]
    if day is not None:
        out = [t for t in out if t.get("day") == day]
    return out


def cmd_list(args: argparse.Namespace) -> int:
    tasks = _read_all()
    rows = _filter_tasks(tasks, args.status, args.priority, args.day)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print(f"(no tasks · status={args.status})")
        return 0
    pad = max((len(t.get("id", "")) for t in rows), default=8)
    for t in rows:
        marker = {"open": "·", "done": "✓", "dropped": "×", "deferred": "→"}.get(t.get("status"), "?")
        age = ""
        if t.get("status") == "open":
            d = int(_seconds_since(t.get("created_at", "")) // 86400)
            age = f"  ({d}d old)" if d else ""
        proof = f"  proof={t.get('proof_ref')}" if t.get("proof_ref") else ""
        print(f"  {marker} {t.get('id', '?'):{pad}s}  [{t.get('priority', '??')}] "
              f"D{t.get('day', '?'):>2}  {t.get('title', '')}{age}{proof}")
    return 0


def audit(tasks: list[dict]) -> dict:
    """Compute stale-task summary · returns {stale: [...], penalty: int, ...}."""
    stale: list[dict] = []
    fresh_open: int = 0
    total_penalty: int = 0
    for t in tasks:
        if t.get("status") != "open":
            continue
        prio = t.get("priority", "P3")
        threshold_days, penalty = STALE_THRESHOLDS.get(prio, (30, 1))
        age_days = _seconds_since(t.get("created_at", "")) / 86400
        if age_days > threshold_days:
            stale.append({
                "id": t.get("id"),
                "priority": prio,
                "title": t.get("title"),
                "age_days": round(age_days, 1),
                "threshold_days": threshold_days,
                "penalty": penalty,
            })
            total_penalty += penalty
        else:
            fresh_open += 1
    return {
        "stale": stale,
        "stale_count": len(stale),
        "fresh_open_count": fresh_open,
        "total_open_count": len(stale) + fresh_open,
        "health_penalty": total_penalty,
        "generated_at": now_iso(),
    }


def cmd_audit(args: argparse.Namespace) -> int:
    tasks = _read_all()
    rep = audit(tasks)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False))
        return 0
    print(f"open tasks: {rep['total_open_count']} "
          f"(fresh={rep['fresh_open_count']} · stale={rep['stale_count']})")
    print(f"health penalty: -{rep['health_penalty']}")
    if rep["stale"]:
        print()
        print("stale tasks (over threshold):")
        for s in rep["stale"]:
            print(f"  ⚠ {s['id']} [{s['priority']}] {s['title']}")
            print(f"      age={s['age_days']}d · threshold={s['threshold_days']}d · -{s['penalty']}")
    return 0


def _announce_scope(overlay: Path, source: str, as_json: bool) -> None:
    """Tell user on stderr which overlay we're acting on.

    Skipped when --json is set (keeps stdout clean for piping). Always
    shown on stderr so it never contaminates stdout even without --json.
    """
    if as_json:
        return
    name = overlay.parent.name or str(overlay.parent)
    if source == "central":
        print(f"  · scope: central  (no .aether/ found walking up from cwd)",
              file=sys.stderr)
    elif source == "discovered":
        print(f"  · scope: {name}", file=sys.stderr)
    elif source == "env":
        print(f"  · scope: {name}  (via env)", file=sys.stderr)
    elif source == "explicit":
        print(f"  · scope: {name}  (via --path)", file=sys.stderr)


def _activate_overlay(explicit: Optional[str]) -> tuple[Path, str]:
    """Resolve active overlay and reassign module globals · return (path, source)."""
    overlay, source = resolve_active_overlay(explicit_path=explicit)
    global DATA_DIR, TASKS_PATH
    DATA_DIR = overlay
    TASKS_PATH = overlay / "tasks.jsonl"
    return overlay, source


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--path",
        help="project root whose .aether/ to use (default: walk up from cwd)",
    )

    ap = argparse.ArgumentParser(
        description="Aether tasks ledger (jsonl)",
        parents=[common],
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", parents=[common], help="add a new task")
    a.add_argument("priority", choices=PRIORITY_VALUES)
    a.add_argument("title")
    a.add_argument("--day", type=int, default=0, help="30-day plan day")
    a.add_argument("--detail", default="")
    a.add_argument("--proof-kind", choices=[v for v in PROOF_KIND_VALUES if v], default=None)
    a.add_argument("--owner", choices=("ai", "owner"), default="ai")
    a.add_argument("--tags", default="")
    a.set_defaults(func=cmd_add)

    c = sub.add_parser("close", parents=[common], help="mark a task done")
    c.add_argument("id")
    c.add_argument("--proof", required=True, help="proof ref · coll-0071 / commit hash / path")
    c.set_defaults(func=cmd_close)

    d = sub.add_parser("defer", parents=[common], help="defer a task to a later day")
    d.add_argument("id")
    d.add_argument("--to-day", type=int, required=True)
    d.set_defaults(func=cmd_defer)

    dr = sub.add_parser("drop", parents=[common], help="drop a task as obsolete")
    dr.add_argument("id")
    dr.add_argument("--reason", default="")
    dr.set_defaults(func=cmd_drop)

    r = sub.add_parser("reopen", parents=[common], help="reopen a closed/dropped task")
    r.add_argument("id")
    r.set_defaults(func=cmd_reopen)

    li = sub.add_parser("list", parents=[common], help="list tasks")
    li.add_argument("--status", default="open",
                    choices=("open", "done", "dropped", "deferred", "all"))
    li.add_argument("--priority", choices=PRIORITY_VALUES, default=None)
    li.add_argument("--day", type=int, default=None)
    li.add_argument("--json", action="store_true")
    li.set_defaults(func=cmd_list)

    au = sub.add_parser("audit", parents=[common], help="show stale tasks · health penalty")
    au.add_argument("--json", action="store_true")
    au.set_defaults(func=cmd_audit)

    args = ap.parse_args()

    overlay, source = _activate_overlay(getattr(args, "path", None))
    _announce_scope(overlay, source, as_json=getattr(args, "json", False))

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
