#!/usr/bin/env python3
"""
aether_guardian.py — 后台守护循环 · 文件丢失预警 + 自动快照 + WIP commit

启动后,每 N 分钟做一次健康检查:
  1) 跑 integrity 看有没有文件丢失 → 丢了立刻警告
  2) 跑 snapshot --if-changed → 有改动才做快照
  3) 可选: 自动 WIP git commit & push 到 backup 分支

**这是无感保护**。启动后你写代码,它在后台静静工作。
Ctrl+C 停止。

用法:
    python bin/aether_guardian.py                 # 默认 15 分钟一轮
    python bin/aether_guardian.py --interval 5    # 5 分钟一轮(节奏快时)
    python bin/aether_guardian.py --with-git      # 加自动 WIP commit + push
    python bin/aether_guardian.py --dry-run       # 只检查不做任何写动作

安全性:
  - WIP commit 都提到独立 branch `wip/auto-backup`, 不会污染你的主 branch
  - 所有动作都日志化到 labs/integrity/guardian.log
  - 发现丢失文件 → 停止自动动作 · 立即报警
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from aether_paths import (
    CENTRAL_OVERLAY,
    CENTRAL_ROOT,
    activate_overlay_for_cli,
    add_path_arg,
)

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = CENTRAL_ROOT                   # back-compat alias
LOG_PATH = ROOT / "labs" / "integrity" / "guardian.log"
BIN = ROOT / "bin"

# Day 13 · overlay-aware · PATH-RESOLUTION-SPEC §3.1
# DATA_DIR / STATE_PATH are reassigned in main() based on --path / cwd-walk.
# `integrity` / `snapshot` / `archive` tasks stay central-only by design
# (they protect Aether source tree itself). `indexer_ingest` / `mirror_digest`
# / `auto_promote` follow the active overlay · see each task for the
# cross-scope data dependency.
DATA_DIR: Path = CENTRAL_OVERLAY
STATE_PATH: Path = DATA_DIR / "guardian-state.json"
ACTIVE_PATH_ARGS: list[str] = []                # forwarded to indexer subprocess
SCOPE_IS_CENTRAL: bool = True                   # gates core-dependent tasks

DEFAULT_INTERVAL_MIN = 15
WIP_BRANCH = "wip/auto-backup"

SCHEDULE_SPEC = {
    "indexer_ingest":   {"every_seconds": 300,      "name": "indexer-ingest"},
    "mirror_digest":    {"every_seconds": 6 * 3600, "name": "mirror-digest"},
    "auto_promote":     {"every_seconds": 24 * 3600,"name": "auto-promote"},
    "archive":          {"every_seconds": 7 * 86400,"name": "archive"},
}


def log(msg: str, level: str = "INFO"):
    stamp = datetime.now(timezone.utc).isoformat()
    line = f"[{stamp}] [{level}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except Exception as e:
        return 1, str(e)


def check_integrity() -> tuple[bool, str]:
    """Return (critical_ok, report).
    critical_ok = True when NO files were deleted.
    Added/modified files are NOT critical (normal evolution) · treated as
    warning and reported but do NOT block schedule tasks.

    Day 13 · central-only (aether_integrity is central-only by design,
    PATH-RESOLUTION-SPEC §3.4). In guest scope this reports OK with a
    skip notice so the loop continues normally.
    """
    if not SCOPE_IS_CENTRAL:
        return True, "OK · integrity is central-only (guest scope · skipped)"
    code, out = run([sys.executable, str(BIN / "aether_integrity.py"), "--json"])
    if "DELETED" in out and code != 0:
        return False, out
    import json
    try:
        data = json.loads(out.strip().splitlines()[-1] if not out.startswith("{") else out)
    except Exception:
        code2, text = run([sys.executable, str(BIN / "aether_integrity.py")])
        has_deleted = "DELETED" in text or "- deleted:" in text
        return not has_deleted, text
    deleted = data.get("deleted", [])
    if deleted:
        return False, f"DELETED: {len(deleted)} files\n" + "\n".join(f"  - {p}" for p in deleted[:10])
    return True, f"OK · added={len(data.get('added', []))} modified={len(data.get('modified', []))}"


def run_snapshot() -> str:
    # Day 13 · snapshot is central-only (packs aether/ source tree · no
    # overlay equivalent). Skip silently in guest scope.
    if not SCOPE_IS_CENTRAL:
        return "(guest scope · snapshot is central-only · skipped)"
    code, out = run([sys.executable, str(BIN / "aether_snapshot.py"), "--if-changed"])
    return out.strip() or f"(exit {code})"


def git_wip_commit() -> str:
    """Commit current WIP to wip/auto-backup branch without disturbing main working branch."""
    # Check if there are changes
    code, out = run(["git", "status", "--porcelain"])
    if not out.strip():
        return "nothing to commit"

    # Get current branch (we'll come back)
    code, current = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current = current.strip()

    # Stash current changes
    code, _ = run(["git", "stash", "push", "-u", "-m", f"guardian-stash-{int(time.time())}"])
    if code != 0:
        return "stash failed"

    try:
        # Checkout (or create) the wip branch
        code, _ = run(["git", "checkout", WIP_BRANCH])
        if code != 0:
            code, _ = run(["git", "checkout", "-b", WIP_BRANCH])
            if code != 0:
                return "could not create wip branch"

        # Apply stash
        run(["git", "stash", "pop"])

        # Stage everything (respects .gitignore)
        run(["git", "add", "-A"])

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = f"wip: auto-backup · {stamp}"
        code, out = run(["git", "commit", "-m", msg])
        if code != 0 and "nothing" in out.lower():
            return "nothing to commit"
        if code != 0:
            return f"commit failed: {out[:200]}"

        # Push (non-fatal if fails)
        code, out = run(["git", "push", "origin", WIP_BRANCH])
        pushed = "pushed" if code == 0 else f"push-failed ({out[:100]})"

        return f"wip commit ok, {pushed}"
    finally:
        # Restore original branch
        run(["git", "checkout", current])
        # Try to restore any remaining stash
        run(["git", "stash", "pop"])


# ─── schedule state ──────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_run": {}}


def save_state(state: dict) -> None:
    """Write guardian-state.json · no-op when content is unchanged.

    Day 11 (coll-0083 Tier-3): previously every run_schedule call wrote
    the file even when no task fired. That meant `aether_hook.py`'s
    15-min guardian tick dirtied the file every tick → git noise →
    unnecessary disk writes. Now we compare content first.
    """
    new_text = json.dumps(state, ensure_ascii=False, indent=2)
    if STATE_PATH.exists():
        try:
            if STATE_PATH.read_text(encoding="utf-8-sig") == new_text:
                return                                  # no change · skip write
        except OSError:
            pass                                         # fall through to write
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        STATE_PATH.write_text(new_text, encoding="utf-8")
    except OSError:
        pass


def should_run(task: str, state: dict, force: bool = False) -> bool:
    if force:
        return True
    spec = SCHEDULE_SPEC.get(task)
    if not spec:
        return False
    last = state.get("last_run", {}).get(task)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return True
    delta = datetime.now(timezone.utc) - last_dt
    return delta.total_seconds() >= spec["every_seconds"]


def mark_ran(task: str, state: dict) -> None:
    state.setdefault("last_run", {})[task] = datetime.now(timezone.utc).isoformat()


# ─── scheduled tasks ─────────────────────────────────────────────────

def task_indexer_ingest(dry_run: bool) -> str:
    if dry_run:
        return "dry-run"
    # Forward --path so indexer writes to the active overlay's index.db ·
    # otherwise guest projects' events never get indexed (Day 13 fix).
    cmd = [sys.executable, str(BIN / "aether_indexer.py"), "ingest", "--quiet"]
    cmd.extend(ACTIVE_PATH_ARGS)
    code, out = run(cmd)
    return f"exit={code}" if code else "ok"


def task_mirror_digest(dry_run: bool) -> str:
    """Run critic · if drift >= HIGH · auto-append a new essence section
    with a 24h-scope semantic summary. Layer A stays git-auditable.

    Day 13 · skipped in guest scope: critic reads central's gen4-fields +
    gen6-coll + gen6-mirror/user-essence.md · those are central-only data.
    Guest overlays don't have a mirror to digest.
    """
    if not SCOPE_IS_CENTRAL:
        return "(guest scope · central-only task · skipped)"
    if not (BIN / "aether_critic.py").exists():
        return "(no critic · skipped)"

    code, out = run([sys.executable, str(BIN / "aether_critic.py"), "--json"])
    try:
        data = json.loads(out.strip())
    except (json.JSONDecodeError, Exception):
        data = None

    drift_level = None
    if isinstance(data, dict):
        drift_level = data.get("drift_level") or data.get("level")
    if not drift_level and out:
        if re.search(r"\bHIGH\b", out):
            drift_level = "HIGH"
        elif re.search(r"\bMEDIUM\b", out):
            drift_level = "MEDIUM"
        elif re.search(r"\bLOW\b", out):
            drift_level = "LOW"

    if drift_level != "HIGH":
        return f"drift={drift_level or '?'} · no append"

    if dry_run:
        return f"drift=HIGH · would append (dry-run)"

    essence = ROOT / "gen6-noesis" / "mirror" / "user-essence.md"
    if not essence.exists():
        return "drift=HIGH but no essence · skipped"

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn_db = DATA_DIR / "index.db"
    if not conn_db.exists():
        return "drift=HIGH but no index.db · skipped (run indexer first)"

    import sqlite3
    conn = sqlite3.connect(f"file:{conn_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    undocumented = set()
    recent_rows = conn.execute(
        "SELECT species_json FROM colls ORDER BY coll_id DESC LIMIT 10"
    ).fetchall()
    for r in recent_rows:
        try:
            for s in json.loads(r["species_json"] or "[]"):
                undocumented.add(s)
        except Exception:
            pass
    registered = {
        r["species_id"] for r in
        conn.execute("SELECT species_id FROM species_registry WHERE is_nursery = 0").fetchall()
    }
    undocumented -= registered

    new_species_rows = conn.execute(
        "SELECT species_id, COUNT(*) AS n FROM species_activations "
        "WHERE fired_at > date('now', '-2 days') GROUP BY species_id ORDER BY n DESC LIMIT 5"
    ).fetchall()
    conn.close()

    section = [
        "",
        f"# {stamp} 自动 digest · guardian drift 修复",
        "",
        f"**触发**: guardian schedule · mirror_digest 检测到 critic drift=HIGH",
        "",
        "## 最近 10 coll 高频物种",
        "",
    ]
    for r in new_species_rows:
        section.append(f"- `{r['species_id']}`: {r['n']} 次 · last 2d")
    if undocumented:
        section.append("")
        section.append("## UNDOCUMENTED species(出现在 coll 但未入 registry)")
        section.append("")
        for s in sorted(undocumented):
            section.append(f"- `{s}` · guardian 建议下次 AI 审阅")

    section.append("")
    section.append(f"*此段由 guardian 在 {datetime.now(timezone.utc).isoformat()} 自动 append ·")
    section.append(" 非手工 · Owner/AI 审阅后可编辑 · 不得删除历史*")
    section.append("")

    try:
        with open(essence, "a", encoding="utf-8") as f:
            f.write("\n".join(section))
    except OSError as e:
        return f"append failed: {e}"
    return f"drift=HIGH · appended {len(new_species_rows)} species lines + {len(undocumented)} undocumented"


def _split_seed_into_fields(seed_id: str, known_fields: set[str]) -> tuple[str, str] | None:
    """Split `seed-<field-a>-<field-b>` correctly when field ids themselves
    contain hyphens(`engineering-rigor`, `cold-to-warm`, `jony-ive` ...).

    Strategy: longest-prefix match against known_fields. For seed
    `seed-engineering-rigor-jony-ive`:
      · try field_a = 'engineering-rigor-jony', field_b = 'ive'  → no
      · try field_a = 'engineering-rigor',     field_b = 'jony-ive' → both known · accept
    Returns (field_a, field_b) on success · None on failure.
    """
    body = seed_id.removeprefix("seed-").removesuffix(".seed")
    parts = body.split("-")
    if len(parts) < 2:
        return None
    # Try every split point, prefer the one where BOTH halves are known
    # fields. Fall back to longest-A-known if no perfect match.
    perfect: tuple[str, str] | None = None
    fallback: tuple[str, str] | None = None
    for i in range(1, len(parts)):
        a = "-".join(parts[:i])
        b = "-".join(parts[i:])
        if a in known_fields and b in known_fields:
            perfect = (a, b)
            break
        if fallback is None and a in known_fields:
            fallback = (a, b)
    return perfect or fallback


def task_auto_promote(dry_run: bool) -> str:
    """Promote nursery seed → species when fields A and B were jointly
    activated ≥ 5 times within 7 days · regardless of whether a species
    of that exact compound id has been registered yet.

    v2 · This was broken before: parser split `seed-engineering-rigor-jony-ive`
    as field_a='engineering' field_b='rigor-jony-ive'(wrong), and also
    required species_activations to already contain a row matching the
    compound name (chicken-and-egg · seed needs activations to be promoted ·
    activations need a registered species to be recorded). Now we look at
    field co-activation in colls, not species_activations.

    Day 13 · skipped in guest scope: species_registry / nursery live under
    central's gen5-ecoware · guest overlays don't maintain their own
    species lifecycle (intentional · see PATH-RESOLUTION-SPEC §5).
    """
    if not SCOPE_IS_CENTRAL:
        return "(guest scope · central-only task · skipped)"
    conn_db = DATA_DIR / "index.db"
    if not conn_db.exists():
        return "(no index.db · skipped)"

    import sqlite3
    conn = sqlite3.connect(f"file:{conn_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    known_fields = {
        r["field_id"] for r in
        conn.execute("SELECT field_id FROM fields_usage").fetchall()
    }
    if not known_fields:
        conn.close()
        return "(no known fields yet · skipped)"

    # Already-registered species — skip seeds whose compound name
    # corresponds to one of these (either a-b or b-a order).
    registered = {
        r["species_id"] for r in
        conn.execute(
            "SELECT species_id FROM species_registry WHERE is_nursery = 0"
        ).fetchall()
    }

    seeds = conn.execute(
        "SELECT species_id FROM species_registry WHERE is_nursery = 1"
    ).fetchall()

    # Pull last-7d colls once · scan in Python for joint activation counts.
    # 63 colls is trivial; no need for SQL gymnastics.
    recent_rows = conn.execute(
        "SELECT coll_id, fields_json FROM colls "
        "WHERE created_at > date('now', '-7 days')"
    ).fetchall()
    recent_field_sets: list[set[str]] = []
    for r in recent_rows:
        try:
            fields = json.loads(r["fields_json"] or "{}")
            # Only count fields with positive concentration (negative means repulsion ·
            # not joint co-activation in the constructive sense).
            recent_field_sets.append({k for k, v in fields.items() if (v or 0) > 0})
        except (json.JSONDecodeError, TypeError):
            continue

    candidates: list[tuple[str, int, str, str]] = []
    skipped: list[str] = []
    duplicates: list[str] = []
    for s in seeds:
        sid = s["species_id"]
        split = _split_seed_into_fields(sid, known_fields)
        if not split:
            skipped.append(f"{sid}(unparsed)")
            continue
        a, b = split
        # Skip if the corresponding species is already registered (in either
        # field order). Such seeds are leftovers from before the seed was
        # first promoted; they should be cleaned up but don't need re-promotion.
        if f"{a}-{b}" in registered or f"{b}-{a}" in registered:
            duplicates.append(sid)
            continue
        n = sum(1 for fset in recent_field_sets if a in fset and b in fset)
        if n >= 5:
            candidates.append((sid, n, a, b))
    conn.close()

    if not candidates:
        bits = []
        if duplicates:
            bits.append(f"{len(duplicates)} duplicate-of-registered")
        if skipped:
            bits.append(f"{len(skipped)} unparsed")
        suffix = f" · {' · '.join(bits)}" if bits else ""
        return f"no candidates{suffix}"

    if dry_run:
        rendered = [f"{sid}({a}+{b}, n={n})" for sid, n, a, b in candidates]
        return f"would promote: {rendered}"

    promoted: list[str] = []
    for sid, n, a, b in candidates:
        if (BIN / "aether_promote.py").exists():
            code, out = run([sys.executable, str(BIN / "aether_promote.py"), "--seed", sid])
            if code == 0:
                promoted.append(f"{sid}(n={n})")
            else:
                log(f"promote {sid} failed: {out[:200]}", level="WARN")
        else:
            log(f"(no aether_promote.py · candidate {sid} logged only)", level="INFO")
            promoted.append(sid + "[manual]")
    return f"promoted: {promoted}"


def task_archive(dry_run: bool) -> str:
    """Cold-tier archival · delegated to aether_archive.py if available.

    Day 13 · central-only: aether_archive operates on central's gen6-noesis
    archive pipeline · no overlay equivalent.
    """
    if not SCOPE_IS_CENTRAL:
        return "(guest scope · central-only task · skipped)"
    if not (BIN / "aether_archive.py").exists():
        return "(no archive tool · skipped)"
    if dry_run:
        return "would run archive"
    code, out = run([sys.executable, str(BIN / "aether_archive.py")])
    return f"exit={code}"


def run_schedule(state: dict, dry_run: bool, force: list[str] | None = None) -> None:
    force = force or []
    tasks = {
        "indexer_ingest": task_indexer_ingest,
        "mirror_digest":  task_mirror_digest,
        "auto_promote":   task_auto_promote,
        "archive":        task_archive,
    }
    for task_name, fn in tasks.items():
        if should_run(task_name, state, force=task_name in force):
            try:
                result = fn(dry_run=dry_run)
                log(f"{task_name}: {result}")
                if not dry_run:
                    mark_ran(task_name, state)
            except Exception as e:
                log(f"{task_name}: exception · {e}", level="WARN")
    save_state(state)


# ─── loop (extended) ─────────────────────────────────────────────────


def guardian_loop(interval_minutes: int, with_git: bool, dry_run: bool, with_schedule: bool = True):
    log(f"guardian started · interval={interval_minutes}min · with_git={with_git} · "
        f"with_schedule={with_schedule} · dry_run={dry_run}")
    log(f"log file: {LOG_PATH.relative_to(ROOT)}")
    log("press Ctrl+C to stop")
    print()

    state = load_state()

    tick = 0
    while True:
        tick += 1
        try:
            log(f"─── tick {tick} ───")
            ok, report = check_integrity()
            log(f"integrity: {report.splitlines()[0] if report else '(no report)'}",
                level=("WARN" if not ok else "INFO"))

            if not ok:
                log("⚠ FILE DELETION DETECTED · pausing auto-actions", level="ALERT")
                log(report[:2000], level="ALERT")
                log("fix the issue or run: python bin/aether_integrity.py --save-baseline",
                    level="ALERT")
            else:
                if not dry_run:
                    snap_result = run_snapshot()
                    log(f"snapshot: {snap_result.splitlines()[0] if snap_result else '(done)'}")

                    if with_git:
                        git_result = git_wip_commit()
                        log(f"git-wip: {git_result}")

                    if with_schedule:
                        run_schedule(state, dry_run=False)
                else:
                    log("(dry-run · skipping snapshot + git)")
                    if with_schedule:
                        run_schedule(state, dry_run=True)

            log(f"sleeping {interval_minutes}min...")
            print()
            time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            log("guardian stopped by user")
            save_state(state)
            return


def _activate_overlay(args) -> None:
    """Reassign module-global paths based on `--path` / cwd-walk.

    Day 13 · PATH-RESOLUTION-SPEC §3.1: guardian is OVERLAY-AWARE for the
    reflex-arc scheduling state (guardian-state.json follows the active
    overlay). Central-only subtasks (integrity / snapshot / mirror_digest
    / auto_promote / archive) gate on SCOPE_IS_CENTRAL and skip in guest
    scope · see individual task docstrings.
    """
    global DATA_DIR, STATE_PATH, ACTIVE_PATH_ARGS, SCOPE_IS_CENTRAL
    overlay, source = activate_overlay_for_cli(
        args, announce=not getattr(args, "dry_run", False),
    )
    DATA_DIR = overlay
    STATE_PATH = overlay / "guardian-state.json"
    if getattr(args, "path", None):
        ACTIVE_PATH_ARGS = ["--path", str(args.path)]
    else:
        ACTIVE_PATH_ARGS = []
    SCOPE_IS_CENTRAL = (overlay.resolve() == CENTRAL_OVERLAY.resolve())


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether file guardian loop.")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MIN,
                    help=f"minutes between checks (default {DEFAULT_INTERVAL_MIN})")
    ap.add_argument("--with-git", action="store_true",
                    help="auto-commit WIP changes to wip/auto-backup branch")
    ap.add_argument("--dry-run", action="store_true",
                    help="integrity checks only, no writes")
    ap.add_argument("--once", action="store_true",
                    help="run one cycle and exit (for cron)")
    ap.add_argument("--no-schedule", action="store_true",
                    help="skip the reflex-layer tasks (indexer ingest · mirror digest · auto promote)")
    ap.add_argument("--force", action="append", default=[],
                    choices=list(SCHEDULE_SPEC.keys()),
                    help="force a specific task to run this tick (can repeat)")
    ap.add_argument("--schedule-status", action="store_true",
                    help="print task last-run status and exit")
    add_path_arg(ap)
    args = ap.parse_args()

    _activate_overlay(args)

    if args.schedule_status:
        state = load_state()
        last = state.get("last_run", {})
        print(f"guardian schedule state · {STATE_PATH}")
        for task, spec in SCHEDULE_SPEC.items():
            ts = last.get(task, "(never)")
            every = spec["every_seconds"]
            print(f"  {task:18s} every {every:6d}s · last_run: {ts}")
        return 0

    with_schedule = not args.no_schedule

    if args.once:
        ok, report = check_integrity()
        print(report)
        if with_schedule:
            state = load_state()
            run_schedule(state, dry_run=args.dry_run, force=args.force)
            if not args.dry_run:
                save_state(state)
        if ok and not args.dry_run:
            print(run_snapshot())
            if args.with_git:
                print(git_wip_commit())
        return 0 if ok else 1

    guardian_loop(args.interval, args.with_git, args.dry_run, with_schedule=with_schedule)
    return 0


if __name__ == "__main__":
    sys.exit(main())
