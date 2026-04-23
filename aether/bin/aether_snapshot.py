#!/usr/bin/env python3
"""
aether_snapshot.py — 本地快照打包器 · **CENTRAL-ONLY**

> **Scope: CENTRAL-ONLY by design** · see `aether/docs/PATH-RESOLUTION-SPEC.md` §3.4
>
> This tool snapshots the Aether source tree itself (bin/, gen4/, gen5/,
> gen6/, gen7/, docs/, site/src/, content/, tools/) — NOT per-project
> overlay data. Guest projects have their own backup story (git /
> OneDrive / project-specific snapshots). Running this from a guest
> project via `--path` would bundle the central Aether source, which
> is never what the caller wants.
>
> If a future need arises to back up `<project>/.aether/`, create a
> separate `aether_overlay_snapshot.py` tool — do NOT add `--path` here.

把所有关键文件打包成独立的 zip,放到 labs/snapshots/,
作为 Git / OneDrive / GitHub 之外的**第四道防线**。

用法:
    python bin/aether_snapshot.py                  # 做一个快照
    python bin/aether_snapshot.py --if-changed     # 只在有改动时才做(对比上次整体哈希)
    python bin/aether_snapshot.py --list           # 列出现有快照
    python bin/aether_snapshot.py --restore <name> # 解压到 /restore/ 供手工对比
    python bin/aether_snapshot.py --cleanup 30     # 删 30 天前的快照

产出:
    labs/snapshots/aether-YYYY-MM-DDTHHMM.zip
    labs/snapshots/meta/<name>.meta.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent              # aether/
WORKSPACE_ROOT = ROOT.parent                                # git repo root
SNAP_DIR = ROOT / "labs" / "snapshots"
META_DIR = SNAP_DIR / "meta"

# What goes into a snapshot (superset of INCLUDE_ROOTS in integrity)
# Paths under aether/ (content layer)
INCLUDE_ROOTS = [
    "bin",
    "gen4-morphogen",
    "gen5-ecoware",
    # v2 · 包含所有私人记忆(仅本地快照 · 不推送 · 防数据丢失第一道防线)
    "gen6-noesis",
    "gen7-logos",
    "00-origin",
    "meta",
    "labs/examples",
    "labs/chronicle",
    "labs/dormant-fields",
    "docs",
    "site/src",
    "site/public",
    "site/astro.config.mjs",
    "site/package.json",
    "site/tsconfig.json",
    "site/.gitignore",
    "content",
    "tools",
]
INCLUDE_TOP = [
    "AGENTS.md", "README.md", "CONTRIBUTING.md", "SECURITY.md",
    "CODE_OF_CONDUCT.md", "PROJECT-MAP.md", "ROADMAP.md", "STRATEGY.md",
    "aether-start.ps1", "start-guardian.ps1",
]

# Paths under workspace root (infrastructure layer)
INCLUDE_ROOTS_WORKSPACE = [
    ".cursor/rules/aether.mdc",
    ".github",
]
INCLUDE_TOP_WORKSPACE = [
    "LICENSE",
    ".gitignore",
    "AGENTS.md",                                             # root pointer
    "README.md",                                             # root pointer
]

EXCLUDE = [
    "node_modules", "__pycache__", ".astro", "site/dist", "site/node_modules",
    ".pytest_cache", ".mypy_cache", "labs/snapshots", ".aether-persona",
    # v2 · 大文件/历史数据仍排除(只保留最近状态)
    "gen6-noesis/archive",  # 已归档,不重复打包
    "labs/integrity/history",  # 历史 integrity 记录
]


def is_excluded(rel_path: str) -> bool:
    return any(pat in rel_path for pat in EXCLUDE)


def collect_files() -> list[tuple[Path, Path]]:
    """Return list of (file_path, archive_base). archive_base decides how the
    file is laid out inside the .zip — workspace-level files get an
    ``workspace/`` prefix so the archive is unambiguous."""
    files: list[tuple[Path, Path]] = []

    def walk(p: Path, base: Path):
        if not p.exists():
            return
        rel = str(p.relative_to(base)).replace("\\", "/")
        if is_excluded(rel):
            return
        if p.is_file():
            files.append((p, base))
        elif p.is_dir():
            try:
                for child in p.iterdir():
                    walk(child, base)
            except PermissionError:
                pass

    for name in INCLUDE_TOP:
        walk(ROOT / name, ROOT)
    for rel in INCLUDE_ROOTS:
        walk(ROOT / rel, ROOT)
    for name in INCLUDE_TOP_WORKSPACE:
        walk(WORKSPACE_ROOT / name, WORKSPACE_ROOT)
    for rel in INCLUDE_ROOTS_WORKSPACE:
        walk(WORKSPACE_ROOT / rel, WORKSPACE_ROOT)
    return files


def compute_fingerprint(files: list[tuple[Path, Path]]) -> str:
    """Fast content fingerprint across all files — for --if-changed."""
    h = hashlib.sha256()
    for p, base in sorted(files, key=lambda x: x[0].as_posix()):
        try:
            stat = p.stat()
            h.update(str(p.relative_to(base)).encode("utf-8"))
            h.update(f"{stat.st_size}:{stat.st_mtime}".encode("utf-8"))
        except OSError:
            continue
    return h.hexdigest()[:16]


def last_fingerprint() -> str | None:
    if not META_DIR.exists():
        return None
    latest = sorted(META_DIR.glob("*.meta.json"), reverse=True)
    if not latest:
        return None
    try:
        data = json.loads(latest[0].read_text(encoding="utf-8"))
        return data.get("fingerprint")
    except (json.JSONDecodeError, OSError):
        return None


def create_snapshot(if_changed: bool = False) -> Path | None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    files = collect_files()
    fp = compute_fingerprint(files)

    if if_changed and fp == last_fingerprint():
        print(f"unchanged since last snapshot (fp={fp}), skipping.", file=sys.stderr)
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    name = f"aether-{stamp}"
    zip_path = SNAP_DIR / f"{name}.zip"
    meta_path = META_DIR / f"{name}.meta.json"

    total_bytes = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p, base in files:
            rel = str(p.relative_to(base)).replace("\\", "/")
            # Workspace-level files get a workspace/ prefix in the archive so
            # they can't collide with content paths like "aether/LICENSE".
            arcname = rel if base == ROOT else f"workspace/{rel}"
            try:
                z.write(p, arcname)
                total_bytes += p.stat().st_size
            except OSError as e:
                print(f"[warn] skipped {arcname}: {e}", file=sys.stderr)

    meta = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "uncompressed_bytes": total_bytes,
        "zip_bytes": zip_path.stat().st_size,
        "fingerprint": fp,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ snapshot: {zip_path.relative_to(ROOT)}")
    print(f"  {len(files)} files · "
          f"{total_bytes/1024:.1f} KB → {zip_path.stat().st_size/1024:.1f} KB (zip)")
    return zip_path


def list_snapshots():
    if not META_DIR.exists():
        print("no snapshots yet")
        return
    metas = sorted(META_DIR.glob("*.meta.json"))
    if not metas:
        print("no snapshots yet")
        return
    print(f"{'name':30s}  {'files':>6s}  {'zip':>10s}  {'when':s}")
    print("-" * 80)
    for m in metas:
        try:
            d = json.loads(m.read_text(encoding="utf-8"))
            print(f"{d['name']:30s}  "
                  f"{d['file_count']:>6d}  "
                  f"{d['zip_bytes']/1024:>7.1f} KB  "
                  f"{d['created_at']}")
        except (json.JSONDecodeError, OSError):
            continue


def cleanup(days: int):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    if not META_DIR.exists():
        return
    for m in META_DIR.glob("*.meta.json"):
        try:
            d = json.loads(m.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
            if created < cutoff:
                zip_path = SNAP_DIR / f"{d['name']}.zip"
                if zip_path.exists():
                    zip_path.unlink()
                m.unlink()
                removed += 1
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    print(f"cleaned {removed} snapshots older than {days} days.")


def restore(name: str):
    zip_path = SNAP_DIR / f"{name}.zip"
    if not zip_path.exists():
        # try with or without prefix
        if not name.startswith("aether-"):
            zip_path = SNAP_DIR / f"aether-{name}.zip"
    if not zip_path.exists():
        print(f"snapshot not found: {name}", file=sys.stderr)
        sys.exit(1)
    restore_dir = ROOT / "restore" / name
    restore_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(restore_dir)
    print(f"✓ restored to {restore_dir.relative_to(ROOT)}")
    print(f"  compare manually, then merge back if needed.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether local snapshot tool.")
    sub = ap.add_subparsers(dest="cmd")

    snap_p = sub.add_parser("snap", help="create a snapshot (default)")
    snap_p.add_argument("--if-changed", action="store_true")

    sub.add_parser("list", help="list existing snapshots")

    cleanup_p = sub.add_parser("cleanup", help="delete old snapshots")
    cleanup_p.add_argument("days", type=int, nargs="?", default=30)

    restore_p = sub.add_parser("restore", help="extract a snapshot")
    restore_p.add_argument("name")

    # Legacy: if no sub-command given, default to snap
    ap.add_argument("--if-changed", action="store_true",
                    help="(alias for 'snap --if-changed')")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--cleanup", type=int, metavar="DAYS")
    ap.add_argument("--restore", metavar="NAME")

    args = ap.parse_args()

    if args.cmd == "list" or args.list:
        list_snapshots()
        return 0
    if args.cmd == "cleanup" or args.cleanup is not None:
        days = args.days if args.cmd == "cleanup" else args.cleanup
        cleanup(days)
        return 0
    if args.cmd == "restore" or args.restore:
        name = args.name if args.cmd == "restore" else args.restore
        restore(name)
        return 0

    if_changed = (args.cmd == "snap" and args.if_changed) or args.if_changed
    create_snapshot(if_changed=if_changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
