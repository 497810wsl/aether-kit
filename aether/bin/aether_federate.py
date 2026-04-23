#!/usr/bin/env python3
"""
aether_federate.py — Core bootstrap / upgrade / status for ~/.aether-core/

Per aether/docs/FEDERATED-MEMORY.md (Day 10 · coll-0082):

    ~/.aether-core/             ← Owner-scope · cross-project core
      core/
        pact.md                 ← from <central>/labs/chronicle/
        fields/**/*.field.md    ← from <central>/gen4-morphogen/fields/
        species-registry.json   ← from <central>/gen5-ecoware/
      manifest.json             ← core_version · built_at · source_central

This CLI manages the core. It does NOT touch per-project overlay
(.aether/handover/ .aether/coll/)· those are aether_project.py's job.

Subcommands:

    aether federate init-core [--apply] [--force]
        Bootstrap ~/.aether-core/ from the current central aether workspace.
        Idempotent: re-run upgrades files only if central's source is newer.
        --force replaces all core files regardless of mtime.

    aether federate status [--json]
        Report core state: exists · version · file count · last built.

    aether federate uninstall [--apply]
        Remove ~/.aether-core/ entirely (asks confirmation unless --apply).

Design (from FEDERATED-MEMORY.md §5 · anti-patterns):
  · NEVER copy gen6-noesis/ or docs/daily/ into core (Owner privacy).
  · NEVER auto-run from aether_install.py · Owner must type it explicitly.
  · Core version is bumped on source schema changes · Day 10 = v1.
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

CORE_DIR = Path.home() / ".aether-core"
CORE_SUBDIR = CORE_DIR / "core"
CORE_MANIFEST = CORE_DIR / "manifest.json"

# Day 10 schema · v1.
# Bump when the core subtree structure changes meaningfully (e.g. add
# core/rules/ or split fields/ into multiple versions).
CORE_VERSION = 1

# Source map · only these paths are copied from central to core.
# Adding a new entry here = extending core. Removing an entry = deprecation.
# Structure: (source_rel_path_from_central, dest_rel_path_under_core/)
CORE_SOURCES: list[tuple[str, str]] = [
    ("aether/labs/chronicle/collaboration-pact-2026-04-17.md", "pact.md"),
    ("aether/gen4-morphogen/fields",                           "fields"),
    # Day 13 form α: gen5-ecoware archived to labs/archive-concepts/ ·
    # species-registry dropped from core (it was always private · 0 external
    # value · and now its source path doesn't exist from central's POV).
    # ("aether/gen5-ecoware/species-registry.json",              "species-registry.json"),  # archived
]

# ANSI · shared with all aether CLIs (Day 12 · coll-0084 Tier-2)
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


# ─── helpers ──────────────────────────────────────────────────────────

def _copy_file(src: Path, dst: Path, force: bool) -> tuple[bool, str]:
    """Copy src → dst if needed. Returns (changed, status)."""
    if not src.exists():
        return False, f"source missing: {src}"
    if dst.exists() and not force:
        try:
            if dst.stat().st_mtime >= src.stat().st_mtime:
                return False, "up-to-date"
        except OSError:
            pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dst)
        return True, "copied"
    except OSError as e:
        return False, f"copy failed: {e}"


def _copy_tree(src: Path, dst: Path, force: bool) -> tuple[int, int, list[str]]:
    """Copy dir tree · returns (copied_count, skipped_count, errors).

    Uses copy2 per-file (preserves mtime · enables up-to-date check next run).
    Ignores __pycache__ · .pyc · _probe_* to match install-time conventions.
    """
    copied = 0
    skipped = 0
    errors: list[str] = []
    if not src.exists() or not src.is_dir():
        return 0, 0, [f"source dir missing: {src}"]
    IGNORE_NAMES = {"__pycache__"}
    IGNORE_PREFIXES = ("_probe_",)
    IGNORE_SUFFIXES = (".pyc",)
    for p in src.rglob("*"):
        if p.is_dir():
            continue
        if p.name in IGNORE_NAMES:
            continue
        if any(p.name.startswith(pr) for pr in IGNORE_PREFIXES):
            continue
        if any(p.name.endswith(sf) for sf in IGNORE_SUFFIXES):
            continue
        rel = p.relative_to(src)
        target = dst / rel
        changed, status = _copy_file(p, target, force)
        if changed:
            copied += 1
        elif status == "up-to-date":
            skipped += 1
        else:
            errors.append(f"{rel}: {status}")
    return copied, skipped, errors


def _read_manifest() -> dict | None:
    if not CORE_MANIFEST.exists():
        return None
    try:
        return json.loads(CORE_MANIFEST.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _write_manifest(stats: dict) -> None:
    CORE_MANIFEST.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── commands ─────────────────────────────────────────────────────────

def cmd_init_core(apply: bool, force: bool, color: bool) -> int:
    print(_c(BOLD, "⟁ aether_federate · init-core", color))
    print()

    # What we WILL do · always show (dry-run default)
    for src_rel, dst_rel in CORE_SOURCES:
        src = WORKSPACE_ROOT / src_rel
        dst = CORE_SUBDIR / dst_rel
        tag = "copy file" if src.is_file() else "copy tree"
        exists = "EXISTS" if dst.exists() else "new"
        print(_c(GRAY, f"  · {tag}  {src_rel}", color))
        print(_c(GRAY, f"          → {dst}  [{exists}]", color))
    print(_c(GRAY, f"  · write manifest  {CORE_MANIFEST}", color))
    print()

    existing = _read_manifest()
    if existing and not force:
        prev_ver = existing.get("core_version")
        print(_c(YELLOW,
            f"  ⚠ core already exists (core_version={prev_ver}) · will upgrade only files whose source is newer", color))
        if prev_ver and prev_ver > CORE_VERSION:
            print(_c(RED, f"  ✕ existing core_version {prev_ver} > this tool's {CORE_VERSION} · refuse to downgrade", color))
            return 2
    if not apply:
        print(_c(YELLOW, "  (dry-run · pass --apply to actually write)", color))
        return 0

    print()
    print(_c(BOLD, "applying...", color))

    CORE_SUBDIR.mkdir(parents=True, exist_ok=True)

    total_copied = 0
    total_skipped = 0
    all_errors: list[str] = []
    files_installed: list[str] = []

    for src_rel, dst_rel in CORE_SOURCES:
        src = WORKSPACE_ROOT / src_rel
        dst = CORE_SUBDIR / dst_rel
        if src.is_file():
            changed, status = _copy_file(src, dst, force)
            if changed:
                total_copied += 1
                files_installed.append(dst_rel)
                print(_c(GREEN, f"  ✓ {dst_rel}", color))
            elif status == "up-to-date":
                total_skipped += 1
                print(_c(GRAY, f"  · {dst_rel} (up-to-date)", color))
            else:
                all_errors.append(f"{src_rel}: {status}")
                print(_c(RED, f"  ✕ {dst_rel}: {status}", color))
        elif src.is_dir():
            copied, skipped, errors = _copy_tree(src, dst, force)
            total_copied += copied
            total_skipped += skipped
            all_errors.extend(errors)
            if copied or skipped:
                files_installed.append(dst_rel + "/")
            sym = GREEN if not errors else YELLOW
            print(_c(sym, f"  {'✓' if not errors else '⚠'} {dst_rel}/  ({copied} copied · {skipped} up-to-date · {len(errors)} err)", color))
        else:
            all_errors.append(f"{src_rel}: source missing")
            print(_c(RED, f"  ✕ {dst_rel}: source missing at {src}", color))

    # Manifest write
    manifest = {
        "core_version": CORE_VERSION,
        "built_at": _now_iso(),
        "source_central": str(WORKSPACE_ROOT.resolve()),
        "files_installed": files_installed,
        "python": sys.executable,
        "stats": {
            "files_copied": total_copied,
            "files_up_to_date": total_skipped,
            "errors": len(all_errors),
        },
    }
    if existing:
        manifest["first_built_at"] = existing.get("first_built_at") or existing.get("built_at")
        manifest["previous_version"] = existing.get("core_version")
    else:
        manifest["first_built_at"] = manifest["built_at"]

    _write_manifest(manifest)
    print(_c(GREEN, f"  ✓ manifest → {CORE_MANIFEST}", color))

    print()
    if all_errors:
        print(_c(YELLOW, f"  ⚠ {len(all_errors)} error(s) · see above · core partially built", color))
        for e in all_errors[:5]:
            print(_c(YELLOW, f"     · {e}", color))
        if len(all_errors) > 5:
            print(_c(YELLOW, f"     · ...({len(all_errors) - 5} more)", color))
    else:
        print(_c(GREEN, f"  core v{CORE_VERSION} ready · {total_copied} new · {total_skipped} up-to-date", color))

    print()
    print(_c(BOLD, "next steps:", color))
    print(_c(GRAY, "  · aether federate status           (verify)", color))
    print(_c(GRAY, "  · aether project init              (per-project overlay)", color))
    print(_c(GRAY, "  · restart Cursor · open any guest project · check status line", color))
    return 0 if not all_errors else 1


def cmd_status(as_json: bool, color: bool) -> int:
    manifest = _read_manifest()
    if as_json:
        out = {
            "core_dir": str(CORE_DIR),
            "exists": CORE_SUBDIR.exists(),
            "manifest": manifest,
        }
        if CORE_SUBDIR.exists():
            try:
                files = [p.relative_to(CORE_SUBDIR).as_posix()
                         for p in CORE_SUBDIR.rglob("*") if p.is_file()]
                out["file_count"] = len(files)
                out["files"] = files[:50]  # cap to stay small
            except Exception:
                pass
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print(_c(BOLD, f"⟁ aether_federate · status · {CORE_DIR}", color))
    print()
    if not CORE_SUBDIR.exists():
        print(_c(YELLOW, "  · no core installed · run: aether federate init-core --apply", color))
        return 0
    if not manifest:
        print(_c(YELLOW, "  ⚠ core dir exists but no manifest · corrupt · re-run init-core", color))
        return 1
    ver = manifest.get("core_version", "?")
    built = manifest.get("built_at", "?")
    first = manifest.get("first_built_at", built)
    src = manifest.get("source_central", "?")
    print(_c(GREEN, f"  ✓ core installed · v{ver}", color))
    print(_c(GRAY, f"     built_at       : {built}", color))
    if first != built:
        print(_c(GRAY, f"     first_built_at : {first}", color))
    print(_c(GRAY, f"     source_central : {src}", color))

    # File count per subtree
    for _, dst_rel in CORE_SOURCES:
        p = CORE_SUBDIR / dst_rel
        if p.is_file():
            print(_c(GREEN, f"     · {dst_rel}  ({p.stat().st_size} bytes)", color))
        elif p.is_dir():
            cnt = sum(1 for q in p.rglob("*") if q.is_file())
            print(_c(GREEN, f"     · {dst_rel}/  ({cnt} files)", color))
        else:
            print(_c(RED, f"     · {dst_rel}  MISSING", color))
    return 0


def cmd_uninstall(apply: bool, color: bool) -> int:
    print(_c(BOLD, f"⟁ aether_federate · uninstall · {CORE_DIR}", color))
    print()
    if not CORE_DIR.exists():
        print(_c(GRAY, "  · no core to remove", color))
        return 0
    print(_c(GRAY, f"  · would remove {CORE_DIR} (entire subtree)", color))
    if not apply:
        print(_c(YELLOW, "  (dry-run · pass --apply to actually delete)", color))
        return 0
    try:
        shutil.rmtree(CORE_DIR)
        print(_c(GREEN, f"  ✓ removed {CORE_DIR}", color))
        return 0
    except OSError as e:
        print(_c(RED, f"  ✕ remove failed: {e}", color))
        return 1


# ─── main ─────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Aether federated memory · core bootstrap / status / uninstall"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-core", help="bootstrap ~/.aether-core/ from central")
    p_init.add_argument("--apply", action="store_true", help="actually do it (default dry-run)")
    p_init.add_argument("--force", action="store_true", help="overwrite even if newer locally")

    p_stat = sub.add_parser("status", help="report core state")
    p_stat.add_argument("--json", action="store_true", dest="as_json")

    p_un = sub.add_parser("uninstall", help="remove ~/.aether-core/ entirely")
    p_un.add_argument("--apply", action="store_true")

    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    color = not args.no_color and sys.stdout.isatty()

    if args.cmd == "init-core":
        return cmd_init_core(args.apply, args.force, color)
    if args.cmd == "status":
        return cmd_status(args.as_json, color)
    if args.cmd == "uninstall":
        return cmd_uninstall(args.apply, color)
    return 2


if __name__ == "__main__":
    sys.exit(main())
