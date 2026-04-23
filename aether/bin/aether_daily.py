#!/usr/bin/env python3
"""
aether_daily.py — daily workspace status · one command · everything you need

Replaces the `selfcheck → query --briefing → tasks list` 3-command morning
ritual with a single readable digest. Intended to be the FIRST thing
Owner / AI runs in any new session after handshake.

Output sections:
  1. STATUS        · selfcheck score · hooks coverage
  2. TASKS         · open · stale · today's recommended next step
  3. MEMORY        · last 3 colls · core memories · recent species hits
  4. REFLEX        · guardian schedule freshness · last hook events
  5. WHATS NEXT    · concrete recommended action(picks highest-ROI task)

Designed for the "I don't want to memorize 22 CLIs" friction surfaced in
coll-0072 / coll-0073. Run this · everything you need · 3 seconds.

Usage:
  python bin/aether_daily.py            # full digest
  python bin/aether_daily.py --short    # 5-line compact (for terminal title bar)
  python bin/aether_daily.py --json     # machine-readable
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Day 11 · overlay-aware (coll-0083 B0-1 fix).
from aether_paths import resolve_active_overlay, CENTRAL_ROOT

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = CENTRAL_ROOT                    # back-compat alias
BIN = ROOT / "bin"

# Overlay to act on · reassigned in main() via --path / env / cwd-walk.
DATA_DIR: Path = CENTRAL_ROOT / ".aether"
ACTIVE_PATH_ARGS: list[str] = []                 # extra args forwarded to
                                                  # aether_tasks subprocesses

# ANSI · shared with all aether CLIs (Day 12 · coll-0084 Tier-2)
import aether_paths as _ap                                       # noqa: E402
RESET  = _ap.RESET
BOLD   = _ap.BOLD
DIM    = _ap.DIM
RED    = _ap.RED
GREEN  = _ap.GREEN
YELLOW = _ap.YELLOW
CYAN   = _ap.CYAN
GRAY   = _ap.GRAY


def _run(args: list[str], timeout: float = 15.0) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8")
        return r.stdout
    except Exception:
        return ""


def _run_json(args: list[str], timeout: float = 15.0) -> dict | list | None:
    out = _run(args, timeout)
    if not out.strip():
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def gather_status() -> dict:
    checks = _run_json([sys.executable, str(BIN / "aether_selfcheck.py"), "--json"]) or []
    if not isinstance(checks, list):
        checks = []
    total = len(checks)
    ok = sum(1 for c in checks if c.get("status") == "ok")
    warn = sum(1 for c in checks if c.get("status") == "warn")
    fail = sum(1 for c in checks if c.get("status") == "fail")
    score = int(ok / total * 100) if total else 0
    # Pull L10 hook coverage if present
    hook_coverage = next((c for c in checks if c.get("layer") == "L10" and "hook" in (c.get("name") or "")), None)
    return {
        "score": score, "ok": ok, "warn": warn, "fail": fail, "total": total,
        "hook_coverage": hook_coverage.get("detail") if hook_coverage else None,
        "warns": [c for c in checks if c.get("status") in ("warn", "fail")],
    }


def gather_tasks() -> dict:
    base = [sys.executable, str(BIN / "aether_tasks.py")] + ACTIVE_PATH_ARGS
    audit = _run_json(base + ["audit", "--json"]) or {}
    open_list = _run_json(base + ["list", "--json"]) or []
    if not isinstance(open_list, list):
        open_list = []
    p0 = [t for t in open_list if t.get("priority") == "P0"]
    p1 = [t for t in open_list if t.get("priority") == "P1"]
    p2 = [t for t in open_list if t.get("priority") == "P2"]
    p3 = [t for t in open_list if t.get("priority") == "P3"]
    return {
        "open_total": audit.get("total_open_count", len(open_list)),
        "stale_count": audit.get("stale_count", 0),
        "stale": audit.get("stale", []),
        "p0": p0, "p1": p1, "p2": p2, "p3": p3,
        "all_open": open_list,
    }


def gather_memory() -> dict:
    """Pull memory snapshot from query --briefing · already structured."""
    briefing = _run([sys.executable, str(BIN / "aether_query.py"), "--briefing"], timeout=8)
    return {"briefing": briefing.strip()}


def gather_reflex() -> dict:
    """Guardian schedule + recent hook events.

    Reads from the active overlay (set by main() via resolve_active_overlay).
    When no project overlay is found this falls back to central's .aether/.
    """
    state_path = DATA_DIR / "guardian-state.json"
    events_path = DATA_DIR / "events.jsonl"
    sched = {}
    if state_path.exists():
        try:
            sched = json.loads(state_path.read_text(encoding="utf-8")).get("last_run", {})
        except Exception:
            pass
    # Stale-detection per task
    now = datetime.now(timezone.utc)
    stale_tasks = []
    SLACK = {"indexer_ingest": 600, "mirror_digest": 8 * 3600,
             "auto_promote": 26 * 3600, "archive": 8 * 86400}
    for name, ts in sched.items():
        try:
            last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age = (now - last).total_seconds()
            if age > SLACK.get(name, 86400):
                stale_tasks.append(f"{name}({int(age)}s)")
        except Exception:
            continue
    # Recent event types · last 30 events
    recent_types: dict[str, int] = {}
    if events_path.exists():
        try:
            with open(events_path, "rb") as f:
                f.seek(max(0, events_path.stat().st_size - 8192))
                tail = f.read().decode("utf-8", errors="replace").splitlines()[-30:]
            for ln in tail:
                try:
                    e = json.loads(ln)
                    t = e.get("type", "?")
                    recent_types[t] = recent_types.get(t, 0) + 1
                except Exception:
                    continue
        except Exception:
            pass
    return {
        "schedule": sched, "stale_tasks": stale_tasks,
        "recent_event_types": recent_types,
        "events_size_kb": (events_path.stat().st_size / 1024) if events_path.exists() else 0,
    }


def recommend_next_action(tasks: dict, status: dict, reflex: dict) -> str:
    """Pick the highest-ROI next thing to do · single line · imperative.

    Order is intentional · most actionable first:
      1. Stale P0       · ledger 已 stale · 必须立刻处理
      2. Selfcheck fail · 系统级故障 · 跑 doctor 看是否一键可修
      3. Stale schedule · reflex 半瘫 · doctor 能修
      4. P0 fresh       · 还没 stale 但是 P0 · 推进
      5. P1 fresh       · 次优先级
      6. Selfcheck warn · 软件健康问题 · doctor 也能看
      7. all green      · 推 P2/P3 或休息
    """
    # 1. Stale P0 → emergency
    stale_p0 = [t for t in tasks.get("stale", []) if t.get("priority") == "P0"]
    if stale_p0:
        return f"🔴 STALE P0(超 3 天): {stale_p0[0]['title']} → 立刻关 / defer / drop"
    # 2. Selfcheck failures · doctor 是首选诊断工具
    if status.get("fail", 0) > 0:
        return (f"🔴 selfcheck {status['fail']} failures · "
                f"跑 `python aether/bin/aether_doctor.py` 一键诊断 + 看是否可 --apply")
    # 3. Stale guardian tasks → doctor 也能 --apply 修
    if reflex.get("stale_tasks"):
        return (f"🟡 reflex schedule stale: {', '.join(reflex['stale_tasks'][:2])} → "
                f"`python aether/bin/aether_doctor.py --apply`")
    # 4. P0 not yet stale but exists → urgency
    if tasks.get("p0"):
        t = tasks["p0"][0]
        return f"🔴 P0 待办: {t['title']} → 推进或 close"
    # 5. P1 if any
    if tasks.get("p1"):
        t = tasks["p1"][0]
        return f"🟡 P1 待办: {t['title']}"
    # 6. Selfcheck warns · doctor 也能修一些
    if status.get("warn", 0) > 0:
        return (f"🟡 selfcheck {status['warn']} warning(s) · "
                f"跑 `python aether/bin/aether_doctor.py` 看是否可一键修复")
    return "🟢 一切就绪 · 拍脑门做 P2 / P3 · 或休息"


def render_full(s: dict, t: dict, m: dict, r: dict, action: str, color: bool) -> str:
    def c(code, text):
        return _ap.c(code, text, color)

    lines = []
    lines.append("")
    lines.append(c(BOLD, f"⟁ Aether daily · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"))
    lines.append("─" * 64)

    score_color = GREEN if s["score"] >= 95 else (YELLOW if s["score"] >= 85 else RED)
    lines.append("")
    lines.append(c(BOLD, "📊 status"))
    lines.append(f"  · health: {c(score_color, str(s['score']) + '/100')} "
                 f"({s['ok']} ok · {s['warn']} warn · {s['fail']} fail)")
    if s.get("hook_coverage"):
        lines.append(f"  · hooks:  {c(CYAN, s['hook_coverage'])}")
    if s["warns"]:
        lines.append(c(DIM, f"  · ⚠ {len(s['warns'])} non-ok check(s) · run aether_selfcheck.py for details"))

    lines.append("")
    lines.append(c(BOLD, "📋 tasks"))
    lines.append(f"  · open: {t['open_total']}  ·  stale: {t['stale_count']}  "
                 f"(P0={len(t['p0'])}, P1={len(t['p1'])}, P2={len(t['p2'])}, P3={len(t['p3'])})")
    if t["stale"]:
        for st in t["stale"][:3]:
            lines.append(c(RED, f"  · 🔴 stale: {st['id']} [{st['priority']}] "
                              f"{st['title']} · age {st['age_days']}d"))
    elif t["p0"] or t["p1"]:
        nxt = (t["p0"] or t["p1"])[0]
        lines.append(c(DIM, f"  · next: {nxt['id']} [{nxt['priority']}] {nxt['title']}"))

    lines.append("")
    lines.append(c(BOLD, "🧠 memory"))
    if m["briefing"]:
        for ln in m["briefing"].splitlines():
            stripped = ln.rstrip()
            if not stripped:
                continue
            if stripped.startswith("##"):
                lines.append(c(CYAN, "  " + stripped.replace("##", "·").strip()))
            else:
                lines.append("  " + stripped)
    else:
        lines.append(c(DIM, "  (briefing unavailable · run aether_indexer.py ingest)"))

    lines.append("")
    lines.append(c(BOLD, "⚡ reflex"))
    rt = r["recent_event_types"]
    if rt:
        type_str = " · ".join(f"{k}={v}" for k, v in sorted(rt.items(), key=lambda x: -x[1])[:6])
        lines.append(f"  · last 30 events: {type_str}")
    lines.append(f"  · events.jsonl: {r['events_size_kb']:.1f} KB")
    if r["stale_tasks"]:
        lines.append(c(YELLOW, f"  · ⚠ guardian stale: {', '.join(r['stale_tasks'])}"))
    else:
        lines.append(c(GREEN, "  · guardian schedule fresh"))

    lines.append("")
    lines.append(c(BOLD, "🎯 next action"))
    lines.append(f"  {action}")
    lines.append("")
    return "\n".join(lines)


def render_short(s: dict, t: dict, action: str) -> str:
    """One-block 5-line compact form."""
    return (
        f"⟁ {s['score']}/100 · {s['ok']}o/{s['warn']}w/{s['fail']}f  "
        f"|  tasks {t['open_total']}o ({len(t['p0'])}P0/{t['stale_count']}stale)\n"
        f"   → {action}"
    )


def render_json(s: dict, t: dict, m: dict, r: dict, action: str) -> str:
    return json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": s,
        "tasks": {k: v for k, v in t.items() if k != "all_open"},
        "memory": m,
        "reflex": r,
        "next_action": action,
    }, ensure_ascii=False, indent=2)


def _autopilot_tick() -> None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from aether_autopilot import maybe_trigger_ingest
        maybe_trigger_ingest()
    except Exception:
        pass


def _activate_overlay(explicit: Optional[str], as_json: bool) -> None:
    """Resolve active overlay, assign globals, print scope banner (stderr)."""
    global DATA_DIR, ACTIVE_PATH_ARGS
    overlay, source = resolve_active_overlay(explicit_path=explicit)
    DATA_DIR = overlay
    if explicit:
        ACTIVE_PATH_ARGS = ["--path", str(explicit)]
    else:
        ACTIVE_PATH_ARGS = []

    if as_json:
        return
    name = overlay.parent.name or str(overlay.parent)
    if source == "central":
        print("  · scope: central  (no .aether/ found walking up from cwd)",
              file=sys.stderr)
    elif source == "discovered":
        print(f"  · scope: {name}", file=sys.stderr)
    elif source == "env":
        print(f"  · scope: {name}  (via env)", file=sys.stderr)
    elif source == "explicit":
        print(f"  · scope: {name}  (via --path)", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether daily digest · one command for the morning ritual")
    ap.add_argument("--short", action="store_true",
                    help="compact 2-line form (e.g. for terminal title bar)")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON output")
    ap.add_argument("--no-color", action="store_true",
                    help="suppress ANSI colors (auto-suppressed when piped)")
    ap.add_argument("--path",
                    help="project root whose .aether/ to read (default: walk up from cwd)")
    args = ap.parse_args()

    _activate_overlay(args.path, as_json=args.json)
    _autopilot_tick()

    s = gather_status()
    t = gather_tasks()
    m = gather_memory()
    r = gather_reflex()
    action = recommend_next_action(t, s, r)

    if args.json:
        print(render_json(s, t, m, r, action))
        return 0
    if args.short:
        print(render_short(s, t, action))
        return 0
    color = not args.no_color and sys.stdout.isatty()
    print(render_full(s, t, m, r, action, color=color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
