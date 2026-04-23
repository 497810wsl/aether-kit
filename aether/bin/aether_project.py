#!/usr/bin/env python3
"""
aether_project.py — Per-project overlay bootstrap / status / uninstall

Per aether/docs/FEDERATED-MEMORY.md (Day 10 · coll-0082):

    <project>/.aether/               ← Project-scope overlay · per project
      handover/day-*-handover.md     ← Per-project day log
      coll/coll-*.md                 ← Per-project collapses
      tasks.jsonl                    ← Per-project task ledger
      events.jsonl                   ← reflex arc (already written by hooks)
      transcripts/, agent-responses/ ← hook snapshots (already)
      manifest.json                  ← scope / init_at / linked_core_version

This CLI manages the overlay. It does NOT touch core (~/.aether-core/) ·
that's aether_federate.py's job.

Subcommands:

    aether project init [--apply] [--path <dir>]
        Bootstrap .aether/ overlay in cwd (or --path). Idempotent: safe to
        re-run. Creates empty handover/ and coll/ subdirs + empty tasks.jsonl
        + manifest.json. Does NOT create handover/coll content itself · that
        happens organically through sessions / hooks.

    aether project status [--json] [--path <dir>]
        Report overlay state: manifest version · handover count · coll count ·
        open tasks. Works from cwd or --path.

    aether project doctor [--apply]
        Check overlay health: linked_core_version still valid · manifest
        schema up-to-date · tasks.jsonl parseable. Fix small issues with
        --apply (e.g. missing subdirs · outdated manifest schema).

    aether project uninstall [--apply]
        Remove .aether/ subtree (double-confirmation because events.jsonl
        may contain 100s of MB of reflex arc history).

Design (from FEDERATED-MEMORY.md §3 · compatibility):
  · Never overwrites existing content (handover/ · coll/ · tasks.jsonl stay)
  · Target must NOT be central aether workspace itself (that's dev-self ·
    its overlay dir already exists without an "init" ceremony)
  · manifest.json bumps overlay_version when schema changes · v1 = Day 10
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent              # aether/
WORKSPACE_ROOT = ROOT.parent                                # central skills

OVERLAY_DIRNAME = ".aether"
OVERLAY_SUBDIRS = ("handover", "coll", "transcripts", "agent-responses", "coll-drafts")
OVERLAY_MANIFEST_NAME = "manifest.json"
TASKS_NAME = "tasks.jsonl"
OVERLAY_VERSION = 1

# ANSI · shared with all aether CLIs (Day 12 · coll-0084 Tier-2)
# The `c as _c` alias keeps this file's existing call-site signature.
import aether_paths as _ap                                       # noqa: E402
RESET  = _ap.RESET
BOLD   = _ap.BOLD
RED    = _ap.RED
GREEN  = _ap.GREEN
YELLOW = _ap.YELLOW
GRAY   = _ap.GRAY
CYAN   = _ap.CYAN
_c     = _ap.c


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── validation ───────────────────────────────────────────────────────

def _resolve_target(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg).expanduser().resolve()
    try:
        import os
        return Path(os.getcwd()).resolve()
    except Exception:
        return Path(".").resolve()


def _validate_target(target: Path) -> tuple[bool, str]:
    if not target.exists():
        return False, f"target does not exist: {target}"
    if not target.is_dir():
        return False, f"target is not a directory: {target}"
    # Prevent init on central aether workspace (already has overlay · would
    # double-initialize and pollute manifest semantics).
    try:
        if target.resolve() == WORKSPACE_ROOT.resolve():
            return False, ("target is the central aether workspace itself · "
                           "its overlay already exists · no init needed")
    except Exception:
        pass
    # Prevent init inside aether/ subtree (would create .aether/ in source code)
    try:
        target.resolve().relative_to(ROOT.resolve())
        return False, f"target is inside aether/ source subtree · pick a real project root"
    except ValueError:
        pass
    return True, ""


# ─── manifest ─────────────────────────────────────────────────────────

def _read_manifest(overlay_dir: Path) -> dict | None:
    p = overlay_dir / OVERLAY_MANIFEST_NAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _read_core_version() -> int | None:
    """Read ~/.aether-core/manifest.json → core_version (for linking)."""
    core_manifest = Path.home() / ".aether-core" / "manifest.json"
    if not core_manifest.exists():
        return None
    try:
        m = json.loads(core_manifest.read_text(encoding="utf-8-sig"))
        v = m.get("core_version")
        return int(v) if isinstance(v, int) else None
    except Exception:
        return None


def _write_manifest(overlay_dir: Path, data: dict) -> None:
    (overlay_dir / OVERLAY_MANIFEST_NAME).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── commands ─────────────────────────────────────────────────────────

def cmd_init(target: Path, apply: bool, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_project · init · {target}", color))
    print()

    ok, reason = _validate_target(target)
    if not ok:
        print(_c(RED, f"  ✕ {reason}", color))
        return 2

    overlay_dir = target / OVERLAY_DIRNAME
    existing = _read_manifest(overlay_dir)
    core_ver = _read_core_version()

    if core_ver is None:
        print(_c(YELLOW,
            "  ⚠ ~/.aether-core/ not installed · overlay will still be created, "
            "but cross-project identity injection will fallback to central · "
            "run `aether federate init-core --apply` to activate core", color))
        print()

    # Compute the delta between current state and desired state.
    # Status lines describe what's ALREADY there (no action needed);
    # actions list ONLY things that would actually be written.
    status_lines: list[str] = []
    actions: list[str] = []

    if overlay_dir.exists():
        status_lines.append(f"overlay dir already present at {overlay_dir}")
    else:
        actions.append(f"create overlay dir {overlay_dir}")

    for sub in OVERLAY_SUBDIRS:
        sp = overlay_dir / sub
        if not sp.exists():
            actions.append(f"mkdir {overlay_dir.name}/{sub}/")

    tasks_path = overlay_dir / TASKS_NAME
    if not tasks_path.exists():
        actions.append(f"touch {overlay_dir.name}/{TASKS_NAME} (empty ledger)")

    mf_path = overlay_dir / OVERLAY_MANIFEST_NAME
    needs_manifest_write = False
    if not mf_path.exists():
        actions.append(f"write {overlay_dir.name}/{OVERLAY_MANIFEST_NAME} (v{OVERLAY_VERSION})")
        needs_manifest_write = True
    elif not existing:
        actions.append(f"rewrite corrupt {overlay_dir.name}/{OVERLAY_MANIFEST_NAME}")
        needs_manifest_write = True
    elif existing.get("overlay_version") != OVERLAY_VERSION:
        actions.append(
            f"upgrade manifest schema v{existing.get('overlay_version')} → v{OVERLAY_VERSION}"
        )
        needs_manifest_write = True
    elif existing.get("linked_core_version") != core_ver:
        actions.append(
            f"relink manifest to core_version={core_ver} "
            f"(was {existing.get('linked_core_version')})"
        )
        needs_manifest_write = True

    for s in status_lines:
        print(_c(GRAY, f"  · {s}", color))

    if not actions:
        if status_lines:
            print()
        print(_c(GREEN, "  ✓ overlay already fully initialized · nothing to do", color))
        return 0

    for a in actions:
        print(_c(GRAY, f"  · would {a}", color))
    print()

    if not apply:
        print(_c(YELLOW, "  (dry-run · pass --apply to actually write)", color))
        return 0

    print(_c(BOLD, "applying...", color))

    overlay_was_new = not overlay_dir.exists()
    overlay_dir.mkdir(parents=True, exist_ok=True)
    if overlay_was_new:
        print(_c(GREEN, f"  ✓ overlay dir {overlay_dir.name}/", color))

    for sub in OVERLAY_SUBDIRS:
        sp = overlay_dir / sub
        if not sp.exists():
            sp.mkdir(parents=True, exist_ok=True)
            print(_c(GREEN, f"  ✓ {overlay_dir.name}/{sub}/", color))

    if not tasks_path.exists():
        tasks_path.write_text("", encoding="utf-8")
        print(_c(GREEN, f"  ✓ {TASKS_NAME}", color))

    if needs_manifest_write:
        # Build manifest · preserve original init_at if upgrading
        manifest: dict = {
            "overlay_version": OVERLAY_VERSION,
            "scope": "project",
            "linked_core_version": core_ver,
            "init_at": _now_iso(),
            "target_root": str(target.resolve()),
            "installed_by": "aether_project.py",
        }
        if existing:
            manifest["init_at"] = existing.get("init_at") or manifest["init_at"]
            prev_ver = existing.get("overlay_version")
            if prev_ver != OVERLAY_VERSION:
                manifest["previous_overlay_version"] = prev_ver
                manifest["last_upgrade_at"] = _now_iso()
        _write_manifest(overlay_dir, manifest)
        print(_c(GREEN, f"  ✓ {OVERLAY_MANIFEST_NAME} (v{OVERLAY_VERSION})", color))

    print()
    print(_c(BOLD, "next steps:", color))
    print(_c(GRAY, f"  · open {target.name} in Cursor · new chat · should show"
                   f" `scope: guest @ {target.name}` with overlay section", color))
    print(_c(GRAY, "  · aether project status           (verify)", color))
    print(_c(GRAY, "  · aether tasks add P0 \"...\"      (add first project task)", color))
    return 0


def cmd_status(target: Path, as_json: bool, color: bool) -> int:
    overlay_dir = target / OVERLAY_DIRNAME
    manifest = _read_manifest(overlay_dir)
    tasks_path = overlay_dir / TASKS_NAME

    # Gather stats
    stats: dict = {
        "target": str(target.resolve()),
        "overlay_dir": str(overlay_dir),
        "exists": overlay_dir.exists(),
        "manifest": manifest,
        "is_central": (target.resolve() == WORKSPACE_ROOT.resolve()),
    }
    if overlay_dir.exists():
        ho_dir = overlay_dir / "handover"
        coll_dir = overlay_dir / "coll"
        stats["handover_count"] = (sum(1 for _ in ho_dir.glob("day-*-handover.md"))
                                    if ho_dir.exists() else 0)
        stats["coll_count"] = (sum(1 for _ in coll_dir.glob("coll-*.md"))
                                if coll_dir.exists() else 0)
        # Task tally
        open_p0 = open_p1 = done = total = 0
        if tasks_path.exists():
            try:
                with open(tasks_path, "r", encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        ln = ln.strip()
                        if not ln:
                            continue
                        try:
                            t = json.loads(ln)
                        except json.JSONDecodeError:
                            continue
                        total += 1
                        if t.get("status") == "open":
                            if t.get("priority") == "P0":
                                open_p0 += 1
                            elif t.get("priority") == "P1":
                                open_p1 += 1
                        elif t.get("status") == "done":
                            done += 1
            except OSError:
                pass
        stats["tasks"] = {
            "total": total, "open_p0": open_p0, "open_p1": open_p1, "done": done,
        }
        events = overlay_dir / "events.jsonl"
        if events.exists():
            try:
                stats["events_bytes"] = events.stat().st_size
            except OSError:
                stats["events_bytes"] = None

    if as_json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    print(_c(BOLD, f"⟁ aether_project · status · {target}", color))
    print()
    if stats["is_central"]:
        print(_c(CYAN,
            "  ! this IS the central aether workspace · overlay is intrinsic · no init required", color))
    if not stats["exists"]:
        print(_c(YELLOW, "  · no overlay yet · run: aether project init --apply", color))
        return 0
    if not manifest:
        if stats["is_central"]:
            # Central's .aether/ is intentionally unmanaged by aether_project
            # (init is firewalled against central). Show a summary only.
            print(_c(GRAY, f"     handover count      : {stats.get('handover_count', 0)}", color))
            print(_c(GRAY, f"     coll count          : {stats.get('coll_count', 0)}", color))
            t = stats.get("tasks", {})
            print(_c(GRAY, f"     tasks               : {t.get('total',0)} total · "
                           f"{t.get('open_p0',0)} open P0 · {t.get('open_p1',0)} open P1 · "
                           f"{t.get('done',0)} done", color))
            return 0
        print(_c(YELLOW, "  ⚠ overlay dir exists but no manifest · corrupt · re-run init", color))
        return 1

    print(_c(GREEN, f"  ✓ overlay v{manifest.get('overlay_version', '?')}", color))
    print(_c(GRAY, f"     init_at             : {manifest.get('init_at', '?')[:19]}", color))
    print(_c(GRAY, f"     linked_core_version : {manifest.get('linked_core_version', 'none')}", color))
    print(_c(GRAY, f"     handover count      : {stats.get('handover_count', 0)}", color))
    print(_c(GRAY, f"     coll count          : {stats.get('coll_count', 0)}", color))
    t = stats.get("tasks", {})
    print(_c(GRAY, f"     tasks               : {t.get('total',0)} total · "
                   f"{t.get('open_p0',0)} open P0 · {t.get('open_p1',0)} open P1 · "
                   f"{t.get('done',0)} done", color))
    eb = stats.get("events_bytes")
    if eb is not None:
        kb = eb // 1024
        print(_c(GRAY, f"     events.jsonl        : {kb} KB", color))

    # Core version mismatch alert
    core_v = _read_core_version()
    linked = manifest.get("linked_core_version")
    if core_v is not None and linked is not None and core_v != linked:
        print()
        print(_c(YELLOW,
            f"  ⚠ linked_core_version ({linked}) ≠ current core_version ({core_v}) · "
            "run `aether project doctor --apply` to relink", color))
    return 0


def cmd_doctor(target: Path, apply: bool, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_project · doctor · {target}", color))
    print()
    overlay_dir = target / OVERLAY_DIRNAME
    if not overlay_dir.exists():
        print(_c(YELLOW, "  · no overlay · run: aether project init --apply", color))
        return 0

    issues: list[tuple[str, str]] = []  # (desc, fix-with-apply-or-manual)

    # Missing subdirs
    for sub in OVERLAY_SUBDIRS:
        if not (overlay_dir / sub).exists():
            issues.append((f"missing subdir: {sub}/", "mkdir on --apply"))

    # Tasks file
    if not (overlay_dir / TASKS_NAME).exists():
        issues.append((f"missing {TASKS_NAME}", "touch on --apply"))

    # Manifest
    manifest = _read_manifest(overlay_dir)
    if not manifest:
        issues.append(("missing/corrupt manifest.json", "rewrite on --apply"))
    else:
        if manifest.get("overlay_version") != OVERLAY_VERSION:
            issues.append((f"overlay_version={manifest.get('overlay_version')} · current={OVERLAY_VERSION}",
                           "rewrite on --apply"))
        core_v = _read_core_version()
        linked = manifest.get("linked_core_version")
        if core_v is not None and linked != core_v:
            issues.append((f"linked_core_version={linked} ≠ core_version={core_v}",
                           "relink on --apply"))

    if not issues:
        print(_c(GREEN, "  ✓ overlay healthy · no issues", color))
        return 0

    for d, fix in issues:
        print(_c(YELLOW, f"  ⚠ {d}   [{fix}]", color))

    if not apply:
        print()
        print(_c(YELLOW, "  (dry-run · pass --apply to fix)", color))
        return 0

    # Apply fixes (idempotent · just re-init)
    print()
    print(_c(BOLD, "fixing...", color))
    return cmd_init(target, apply=True, color=color)


def cmd_uninstall(target: Path, apply: bool, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_project · uninstall · {target}", color))
    print()
    overlay_dir = target / OVERLAY_DIRNAME
    if not overlay_dir.exists():
        print(_c(GRAY, "  · no overlay to remove", color))
        return 0

    try:
        size = sum(p.stat().st_size for p in overlay_dir.rglob("*") if p.is_file())
        mb = size / (1024 * 1024)
    except Exception:
        mb = 0.0

    print(_c(YELLOW, f"  · will remove {overlay_dir} (~{mb:.1f} MB)", color))
    print(_c(GRAY, "     this deletes: manifest · handover/ · coll/ · tasks.jsonl · "
                   "events.jsonl · transcripts/ · agent-responses/", color))
    if not apply:
        print(_c(YELLOW, "  (dry-run · pass --apply to actually delete)", color))
        return 0

    try:
        shutil.rmtree(overlay_dir)
        print(_c(GREEN, f"  ✓ removed {overlay_dir}", color))
        return 0
    except OSError as e:
        print(_c(RED, f"  ✕ remove failed: {e}", color))
        return 1


# ─── main ─────────────────────────────────────────────────────────────

def main() -> int:
    # Shared options · attached to the top-level parser AND to every subparser
    # so `--no-color` / `--path` can appear either before or after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-color", action="store_true",
                        help="disable ANSI color (accepted anywhere on the line)")
    common.add_argument("--path", help="target project root (default cwd)")

    ap = argparse.ArgumentParser(
        description="Aether per-project overlay · init / status / doctor / uninstall",
        parents=[common],
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", parents=[common],
                            help="bootstrap .aether/ overlay in cwd or --path")
    p_init.add_argument("--apply", action="store_true")

    p_stat = sub.add_parser("status", parents=[common], help="report overlay state")
    p_stat.add_argument("--json", action="store_true", dest="as_json")

    p_doc = sub.add_parser("doctor", parents=[common],
                           help="check + fix overlay health")
    p_doc.add_argument("--apply", action="store_true")

    p_un = sub.add_parser("uninstall", parents=[common],
                          help="remove .aether/ overlay")
    p_un.add_argument("--apply", action="store_true")

    args = ap.parse_args()

    color = not args.no_color and sys.stdout.isatty()
    target = _resolve_target(getattr(args, "path", None))

    if args.cmd == "init":
        return cmd_init(target, args.apply, color)
    if args.cmd == "status":
        return cmd_status(target, args.as_json, color)
    if args.cmd == "doctor":
        return cmd_doctor(target, args.apply, color)
    if args.cmd == "uninstall":
        return cmd_uninstall(target, args.apply, color)
    return 2


if __name__ == "__main__":
    sys.exit(main())
