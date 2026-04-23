#!/usr/bin/env python3
"""
aether_doctor.py — 一键体检 + 安全修复

NPM 的 `npm doctor` 思想 · 适用于 Aether workspace。诊断阶段 read-only ·
修复阶段需要显式 `--apply` · critical 问题永远不自动修(怕越修越坏)。

为什么这个工具(coll-0076 真实痛点):

  · 22 个 CLI · 每个负责一块 · 出问题时 Owner 要记得"指标 X 看 Y CLI"
  · selfcheck 告诉你"L9 stale" · 但不告诉你"运行 aether_tasks.py audit 然后 close"
  · payload-schema 告诉你"unused field" · 但不告诉你"加进 KNOWN_CONSUMED"
  · 一行命令 · 自动诊断 + 给出明确 fix 建议 + 可一键执行安全的修法

诊断项(6 类 · 自动跑):
  1. SCHEMA       · index.db 是否 schema-up-to-date
  2. STALE        · guardian schedule task 上次跑时间
  3. ORPHANS      · nursery seed 是否对应已注册 species(superseded)
  4. UNUSED       · payload schema 检测到的未消费字段
  5. INTEGRITY    · file integrity baseline 是否还匹配
  6. LEDGER       · tasks.jsonl 健康(stale P0 / 异常 status)

修复模式(--apply):
  · minor    自动修(consolidate alias / cleanup superseded seed)
  · major    自动修但记 lifecycle log(rebuild index / run guardian --once)
  · critical 永不自动修(integrity baseline mismatch · DB corruption)

CLI:
  python bin/aether_doctor.py            # 诊断 only · 红黄绿 + fix 提示
  python bin/aether_doctor.py --apply    # 真修 minor + major · critical 不动
  python bin/aether_doctor.py --json     # 机器输出
  python bin/aether_doctor.py check      # exit 0/1/2 给 cron / CI

设计原则:
  1. 0 依赖 · stdlib only
  2. dry-run by default · 永不破坏
  3. 每个修复对应一个 reversible 操作(aether_*.py 已有的子命令)· 不发明新副作用
  4. 诊断 ≤ 5 秒(read-only · 慢操作走 --deep)
  5. fix 提示明确到具体命令(Owner 不需要查文档)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aether_paths import resolve_active_overlay, CENTRAL_ROOT

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = CENTRAL_ROOT
BIN = ROOT / "bin"
# Day 11: DATA_DIR is resolved at main() time · may point to project overlay.
DATA_DIR: Path = CENTRAL_ROOT / ".aether"

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

SEVERITY_ORDER = {"ok": 0, "minor": 1, "major": 2, "critical": 3}


@dataclass
class Diagnosis:
    name: str
    severity: str  # ok / minor / major / critical
    detail: str = ""
    fix_command: Optional[list[str]] = None    # what `--apply` would run
    fix_explanation: str = ""                  # human-readable
    auto_apply: bool = False                   # major+ may need confirmation
    extra: dict = field(default_factory=dict)

    def symbol(self) -> str:
        return {"ok": "✓", "minor": "·", "major": "⚠", "critical": "✕"}[self.severity]

    def color(self) -> str:
        return {"ok": GREEN, "minor": CYAN, "major": YELLOW, "critical": RED}[self.severity]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "severity": self.severity,
            "detail": self.detail,
            "fix_command": self.fix_command,
            "fix_explanation": self.fix_explanation,
            "auto_apply": self.auto_apply,
            **self.extra,
        }


# ─── helpers ────────────────────────────────────────────────────────

def _run(args: list[str], timeout: float = 30.0) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8")
        return (r.returncode, (r.stdout or "") + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        return (1, "(timeout)")
    except Exception as e:
        return (1, f"(error: {e})")


def _run_json(args: list[str], timeout: float = 30.0) -> dict | list | None:
    rc, out = _run(args, timeout)
    if not out.strip():
        return None
    try:
        return json.loads(out.strip().splitlines()[-1] if out.strip().startswith("{") is False else out)
    except Exception:
        try:
            return json.loads(out)
        except Exception:
            return None


# ─── 6 checks ───────────────────────────────────────────────────────

def check_schema() -> Diagnosis:
    """Is .aether/index.db present + has the expected tables?"""
    db = DATA_DIR / "index.db"
    # Day 13 · fix_command now forwards --path so rebuild targets the SAME
    # overlay doctor was invoked on. Before this, doctor in a guest project
    # would diagnose the guest overlay correctly but --apply would rebuild
    # central's index.db. See PATH-RESOLUTION-SPEC §6.2.
    overlay_path_args = ["--path", str(DATA_DIR.parent)]
    if not db.exists():
        return Diagnosis(
            name="SCHEMA",
            severity="major",
            detail="index.db missing · B layer not built",
            fix_command=[sys.executable, str(BIN / "aether_indexer.py"), "rebuild"] + overlay_path_args,
            fix_explanation="rebuild SQLite index from A layer markdown",
            auto_apply=True,
        )
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        present = {r[0] for r in rows}
    except Exception as e:
        return Diagnosis(
            name="SCHEMA", severity="critical",
            detail=f"index.db unreadable: {e}",
            fix_command=[sys.executable, str(BIN / "aether_indexer.py"), "rebuild"] + overlay_path_args,
            fix_explanation="DB corrupted · need rebuild but verify backup first",
            auto_apply=False,
        )
    expected = {"events", "memories", "memories_fts", "colls", "fields_usage",
                "species_activations", "species_registry", "files_meta", "digests"}
    missing = expected - present
    if missing:
        return Diagnosis(
            name="SCHEMA", severity="major",
            detail=f"missing tables: {sorted(missing)}",
            fix_command=[sys.executable, str(BIN / "aether_indexer.py"), "rebuild"] + overlay_path_args,
            fix_explanation="schema drift · rebuild from A layer",
            auto_apply=True,
        )
    return Diagnosis(name="SCHEMA", severity="ok",
                     detail=f"all {len(expected)} tables present")


def check_stale_schedule() -> Diagnosis:
    """Are guardian scheduled tasks running on time?"""
    state_path = DATA_DIR / "guardian-state.json"
    overlay_path_args = ["--path", str(DATA_DIR.parent)]
    if not state_path.exists():
        return Diagnosis(
            name="STALE", severity="minor",
            detail="guardian-state.json missing · never ran",
            fix_command=[sys.executable, str(BIN / "aether_guardian.py"), "--once"] + overlay_path_args,
            fix_explanation="run guardian once to seed state",
            auto_apply=True,
        )
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return Diagnosis(
            name="STALE", severity="minor",
            detail="guardian-state.json malformed",
            fix_command=[sys.executable, str(BIN / "aether_guardian.py"), "--once"] + overlay_path_args,
            fix_explanation="re-run guardian to rewrite state",
            auto_apply=True,
        )
    last = state.get("last_run", {})
    SLACK = {"indexer_ingest": 600, "mirror_digest": 8 * 3600,
             "auto_promote": 26 * 3600, "archive": 8 * 86400}
    now = datetime.now(timezone.utc)
    stale: list[str] = []
    for name, ts in last.items():
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age = (now - dt).total_seconds()
            if age > SLACK.get(name, 86400):
                stale.append(f"{name}({int(age // 60)}m)")
        except Exception:
            stale.append(f"{name}(unparseable)")
    if not stale:
        return Diagnosis(name="STALE", severity="ok",
                         detail=f"{len(last)} tasks all fresh")
    return Diagnosis(
        name="STALE", severity="minor",
        detail=f"stale tasks: {', '.join(stale)}",
        fix_command=[sys.executable, str(BIN / "aether_guardian.py"), "--once"] + overlay_path_args,
        fix_explanation="run all schedule tasks now",
        auto_apply=True,
    )


def check_orphan_seeds() -> Diagnosis:
    """Nursery seeds whose corresponding species is already registered.

    Day 13 form α · aether_seeds.py archived to labs/archive-cli/ · this check
    is now a no-op under form α(species concept retired)· report ok and explain.
    """
    seeds_tool = BIN / "aether_seeds.py"
    if not seeds_tool.exists():
        return Diagnosis(name="ORPHANS", severity="ok",
                         detail="(archived · form α · aether_seeds in labs/archive-cli/ · check not applicable)")
    rc, out = _run([sys.executable, str(seeds_tool), "cleanup"])
    if "nothing to clean" in out:
        return Diagnosis(name="ORPHANS", severity="ok",
                         detail="no superseded seeds")
    # Extract count
    import re
    m = re.search(r"would supersede (\d+) seed", out)
    n = int(m.group(1)) if m else 0
    if n == 0:
        return Diagnosis(name="ORPHANS", severity="ok",
                         detail="no orphan seeds")
    return Diagnosis(
        name="ORPHANS", severity="minor",
        detail=f"{n} seed(s) superseded by registered species",
        fix_command=[sys.executable, str(seeds_tool), "cleanup", "--apply"],
        fix_explanation=f"move {n} obsolete seed(s) to labs/death-graveyard/seeds/",
        auto_apply=True,
        extra={"orphan_count": n},
    )


def check_unused_fields() -> Diagnosis:
    """Cursor payload fields present in samples but not in KNOWN_CONSUMED."""
    schema_tool = BIN / "aether_payload_schema.py"
    if not schema_tool.exists():
        return Diagnosis(name="UNUSED", severity="ok",
                         detail="(schema tool missing · skipping)")
    data = _run_json([sys.executable, str(schema_tool), "--json"])
    if not isinstance(data, dict):
        return Diagnosis(name="UNUSED", severity="minor",
                         detail="payload schema audit failed",
                         fix_command=[sys.executable, str(schema_tool)],
                         fix_explanation="re-run schema discovery",
                         auto_apply=False)
    n = data.get("unused_field_count", 0)
    by_event = data.get("unused_by_event", {})
    if n == 0:
        return Diagnosis(name="UNUSED", severity="ok",
                         detail=f"0 unused · {len(data.get('events', {}))} events scanned")
    severity = "major" if n >= 3 else "minor"
    bits = ", ".join(f"{ev}:{','.join(fs[:2])}" for ev, fs in list(by_event.items())[:3])
    return Diagnosis(
        name="UNUSED", severity=severity,
        detail=f"{n} unused · {bits}",
        fix_command=None,  # cannot auto-fix · needs code change
        fix_explanation=("consume these fields in aether_hook.py + add to KNOWN_CONSUMED_FIELDS · "
                         "see aether/docs/hook-payload-schema.md"),
        auto_apply=False,
        extra={"unused_count": n, "by_event": by_event},
    )


def check_integrity() -> Diagnosis:
    """File integrity baseline still matches?"""
    integrity_tool = BIN / "aether_integrity.py"
    if not integrity_tool.exists():
        return Diagnosis(name="INTEGRITY", severity="ok",
                         detail="(integrity tool missing · skipping)")
    rc, out = _run([sys.executable, str(integrity_tool), "--json"])
    # Parse · last line should be JSON
    try:
        last_line = out.strip().splitlines()[-1] if out.strip() else "{}"
        data = json.loads(last_line)
    except Exception:
        # Plain text fallback
        if "DELETED" in out or "deleted:" in out:
            return Diagnosis(
                name="INTEGRITY", severity="critical",
                detail="files were deleted since last baseline",
                fix_command=None,
                fix_explanation="manual review required · check git log for the deletes ·"
                                " if intentional, run aether_integrity.py --save-baseline",
                auto_apply=False,
            )
        return Diagnosis(name="INTEGRITY", severity="ok",
                         detail="(no parseable output · assume ok)")
    deleted = data.get("deleted", [])
    added = data.get("added", [])
    modified = data.get("modified", [])
    if deleted:
        return Diagnosis(
            name="INTEGRITY", severity="critical",
            detail=f"{len(deleted)} deleted · {len(modified)} modified · {len(added)} added",
            fix_command=None,
            fix_explanation="if deletes are intentional · run "
                            "`python bin/aether_integrity.py --save-baseline` ·"
                            " never auto-apply · this is a Owner decision",
            auto_apply=False,
            extra={"deleted_count": len(deleted), "deleted": deleted[:5]},
        )
    if added or modified:
        return Diagnosis(
            name="INTEGRITY", severity="minor",
            detail=f"{len(added)} added · {len(modified)} modified · 0 deleted",
            fix_command=[sys.executable, str(integrity_tool), "--save-baseline"],
            fix_explanation="refresh baseline to acknowledge normal evolution",
            auto_apply=False,  # not safe to auto · loses delete-detection power
        )
    return Diagnosis(name="INTEGRITY", severity="ok",
                     detail="baseline matches · 0 drift")


def check_ledger() -> Diagnosis:
    """tasks.jsonl health · stale P0 = critical · stale P1 = major."""
    tasks_tool = BIN / "aether_tasks.py"
    if not tasks_tool.exists():
        return Diagnosis(name="LEDGER", severity="ok",
                         detail="(tasks tool missing · skipping)")
    data = _run_json([sys.executable, str(tasks_tool), "audit", "--json"])
    if not isinstance(data, dict):
        return Diagnosis(name="LEDGER", severity="minor",
                         detail="tasks audit failed")
    stale = data.get("stale", [])
    if not stale:
        return Diagnosis(name="LEDGER", severity="ok",
                         detail=f"{data.get('total_open_count', 0)} open · 0 stale")
    by_prio = {"P0": [], "P1": [], "P2": [], "P3": []}
    for s in stale:
        by_prio.setdefault(s.get("priority", "P3"), []).append(s)
    if by_prio["P0"]:
        sev = "critical"
        bits = ", ".join(f"{s['id']}({s['age_days']}d)" for s in by_prio["P0"][:3])
        msg = f"{len(by_prio['P0'])} stale P0 · {bits}"
    elif by_prio["P1"]:
        sev = "major"
        bits = ", ".join(f"{s['id']}({s['age_days']}d)" for s in by_prio["P1"][:3])
        msg = f"{len(by_prio['P1'])} stale P1 · {bits}"
    else:
        sev = "minor"
        bits = ", ".join(f"{s['id']}({s['age_days']}d)" for s in stale[:3])
        msg = f"{len(stale)} stale (P2+) · {bits}"
    return Diagnosis(
        name="LEDGER", severity=sev, detail=msg,
        fix_command=None,
        fix_explanation="`aether_tasks.py close <id> --proof <ref>` "
                        "or `defer --to-day <N>` or `drop --reason <text>`",
        auto_apply=False,
        extra={"stale_count": len(stale)},
    )


CHECKS = [
    ("SCHEMA",    check_schema),
    ("STALE",     check_stale_schedule),
    ("ORPHANS",   check_orphan_seeds),
    ("UNUSED",    check_unused_fields),
    ("INTEGRITY", check_integrity),
    ("LEDGER",    check_ledger),
]


# ─── orchestration ──────────────────────────────────────────────────

def diagnose() -> list[Diagnosis]:
    return [fn() for _, fn in CHECKS]


def apply_fixes(diags: list[Diagnosis]) -> list[tuple[Diagnosis, int, str]]:
    """Run fix_command for each minor + major diag with fix_command set.

    critical diagnoses are NEVER auto-applied · we just report them.
    Returns list of (diagnosis, exit_code, output).
    """
    results: list[tuple[Diagnosis, int, str]] = []
    for d in diags:
        if d.severity in ("ok", "critical"):
            continue
        if not d.fix_command:
            continue
        if not d.auto_apply:
            continue
        rc, out = _run(d.fix_command, timeout=60)
        results.append((d, rc, out))
    return results


def render_text(diags: list[Diagnosis], color: bool = True) -> str:
    def c(code, text):
        return _ap.c(code, text, color)

    lines = []
    lines.append("")
    lines.append(c(BOLD, f"⟁ Aether doctor · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"))
    lines.append("─" * 64)
    lines.append("")

    by_sev = {"critical": 0, "major": 0, "minor": 0, "ok": 0}
    for d in diags:
        by_sev[d.severity] = by_sev.get(d.severity, 0) + 1

    for d in diags:
        marker = c(d.color(), d.symbol())
        lines.append(f"  {marker}  {c(BOLD, d.name):20s}  {d.detail}")
        if d.severity != "ok":
            lines.append(f"       {c(GRAY, '↳ fix:')} {c(DIM, d.fix_explanation)}")
            if d.fix_command and d.auto_apply:
                lines.append(f"       {c(GRAY, '  cmd:')} {c(DIM, ' '.join(d.fix_command[1:]))}")

    lines.append("")
    lines.append("─" * 64)
    sev_str = (
        f"{c(GREEN, str(by_sev['ok']) + ' ok')} · "
        f"{c(CYAN, str(by_sev['minor']) + ' minor')} · "
        f"{c(YELLOW, str(by_sev['major']) + ' major')} · "
        f"{c(RED, str(by_sev['critical']) + ' critical')}"
    )
    auto_fixable = sum(1 for d in diags if d.severity in ("minor", "major")
                       and d.fix_command and d.auto_apply)
    lines.append(f"{c(BOLD, 'summary:')} {sev_str}")
    if auto_fixable:
        lines.append(f"  {c(YELLOW, '→ ' + str(auto_fixable) + ' issue(s) auto-fixable')} · "
                     f"run with {c(BOLD, '--apply')} to fix them")
    elif by_sev["critical"]:
        lines.append(f"  {c(RED, '✕ critical issue(s) need manual review')} · see fix hints above")
    elif by_sev["major"]:
        lines.append(f"  {c(YELLOW, '⚠ major issue(s) need manual fix')} · see fix hints above")
    else:
        lines.append(c(GREEN, "  ✓ system healthy"))
    lines.append("")
    return "\n".join(lines)


def render_apply_results(results: list[tuple[Diagnosis, int, str]], color: bool = True) -> str:
    def c(code, text):
        return _ap.c(code, text, color)

    if not results:
        return c(GREEN, "  ✓ no auto-fixable issues") + "\n"
    lines = [c(BOLD, "applying fixes...")]
    for d, rc, out in results:
        status = c(GREEN, "✓") if rc == 0 else c(RED, "✕")
        lines.append(f"  {status}  {d.name}: {d.fix_explanation}")
        if rc != 0:
            tail = (out.strip().splitlines() or ["(no output)"])[-1][:120]
            lines.append(f"       {c(GRAY, 'output:')} {tail}")
    return "\n".join(lines)


def cmd_check() -> int:
    """For cron / CI · exit 0 (ok) · 1 (critical) · 2 (major+) · 3 (minor+)."""
    diags = diagnose()
    worst = max((SEVERITY_ORDER[d.severity] for d in diags), default=0)
    by_sev = {}
    for d in diags:
        by_sev[d.severity] = by_sev.get(d.severity, 0) + 1
    print(f"doctor: {by_sev.get('critical', 0)}c · {by_sev.get('major', 0)}M · "
          f"{by_sev.get('minor', 0)}m · {by_sev.get('ok', 0)}o")
    return {0: 0, 1: 3, 2: 2, 3: 1}.get(worst, 0)


def _autopilot_tick() -> None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from aether_autopilot import maybe_trigger_ingest
        maybe_trigger_ingest()
    except Exception:
        pass


def _activate_overlay(explicit: Optional[str], as_json: bool) -> None:
    global DATA_DIR
    overlay, source = resolve_active_overlay(explicit_path=explicit)
    DATA_DIR = overlay
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
    ap = argparse.ArgumentParser(description="Aether one-command health check + safe auto-fix")
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--apply", action="store_true",
                    help="actually run safe fixes for minor/major issues")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON")
    ap.add_argument("--no-color", action="store_true",
                    help="suppress ANSI colors")
    ap.add_argument("--path",
                    help="project root whose .aether/ to check (default: walk up from cwd)")

    # Hidden subcommand for cron / CI
    sub.add_parser("check", help="exit 0/1/2/3 for cron · brief stdout summary")

    args = ap.parse_args()

    _activate_overlay(args.path, as_json=args.json)
    _autopilot_tick()

    if args.cmd == "check":
        return cmd_check()

    diags = diagnose()

    if args.json:
        print(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "diagnoses": [d.to_dict() for d in diags],
            "summary": {
                sev: sum(1 for d in diags if d.severity == sev)
                for sev in ("ok", "minor", "major", "critical")
            },
        }, ensure_ascii=False, indent=2))
        return 0

    color = not args.no_color and sys.stdout.isatty()
    print(render_text(diags, color=color))

    if args.apply:
        results = apply_fixes(diags)
        print(render_apply_results(results, color=color))
        # Re-diagnose to show post-fix state
        if results:
            print()
            print(render_text(diagnose(), color=color))
            print()

    worst = max((SEVERITY_ORDER[d.severity] for d in diags), default=0)
    return 0 if worst <= 1 else (2 if worst == 2 else 1)


if __name__ == "__main__":
    sys.exit(main())
