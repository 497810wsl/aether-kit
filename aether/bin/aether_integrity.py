#!/usr/bin/env python3
"""
aether_integrity.py — 数据完整性校验器 · **CENTRAL-ONLY**

> **Scope: CENTRAL-ONLY by design** · see `aether/docs/PATH-RESOLUTION-SPEC.md` §3.4
>
> The baseline is a SHA256 fingerprint of the Aether source tree itself
> (bin/, gen4/, gen5/, gen6/mirror/, gen7/, docs/, site/src/, content/,
> `.cursor/rules/aether.mdc`, LICENSE). This is what detects `git restore`
> gone wrong, StrReplace truncation bugs, and Cursor Windows cache
> corruption that eats files. Per-project overlay contents are not
> in scope — they're mutable work product, not immutable source.
>
> If a future need arises for per-project integrity checks, create a
> separate tool — do NOT add `--path` here.

扫描所有关键文件,计算 SHA256 哈希,产出清单。
对比上次基线,报告:
  - 新增的文件 (A)
  - 丢失的文件 (D)  ← 最关键:如果真丢了,这里能立即发现
  - 内容改变的文件 (M)
  - 未变的文件 (ok)

用法:
    python bin/aether_integrity.py                # 扫描 + 对比上次基线
    python bin/aether_integrity.py --save-baseline # 把当前状态存为新基线
    python bin/aether_integrity.py --json         # 输出 JSON 给脚本消费
    python bin/aether_integrity.py --verbose      # 列出所有 ok 的文件(默认只列 A/D/M)

产出:
    labs/integrity/baseline.json    (上次保存的基线)
    labs/integrity/latest.json      (本次扫描结果)
    labs/integrity/history/YYYY-MM-DD-HHMMSS.json (历史)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _prune_history(history_dir: Path, keep_latest: int = 50) -> int:
    """Keep only the `keep_latest` newest history snapshots · delete rest.

    Day 11 · prevents history/ from growing forever. Before this fix every
    invocation wrote a new file and nothing deleted old ones. Over Day 1-10
    the directory accumulated ~15 files; long-term it would hit thousands.
    """
    try:
        files = sorted(history_dir.glob("*.json"), reverse=True)
    except OSError:
        return 0
    if len(files) <= keep_latest:
        return 0
    deleted = 0
    for old in files[keep_latest:]:
        try:
            old.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted

ROOT = Path(__file__).resolve().parent.parent              # aether/
WORKSPACE_ROOT = ROOT.parent                                # git repo root
OUT_DIR = ROOT / "labs" / "integrity"
BASELINE_PATH = OUT_DIR / "baseline.json"
LATEST_PATH = OUT_DIR / "latest.json"
HISTORY_DIR = OUT_DIR / "history"

# Directories to include under aether/ (the content root)
# Day 13 form α: gen5-ecoware · gen7-logos · gen6-noesis/critique · gen6-noesis/
# evolution-proposals · gen4-morphogen/pro-fields ALL moved to labs/archive-*.
# Baseline now tracks the live content + the archive · so anything that moved
# today doesn't register as DELETED on next guardian tick.
INCLUDE_ROOTS = [
    "bin",
    "gen4-morphogen",
    "gen6-noesis/mirror",
    "gen6-noesis/resonance-map.md",
    "00-origin",
    "meta",
    "labs/examples",
    "labs/chronicle",
    "labs/archive-concepts",            # Day 13 form α archives
    "labs/archive-cli",                 # Day 13 archived CLIs
    "docs",
    "site/src",
    "site/public",
    "site/astro.config.mjs",
    "site/package.json",
    "site/tsconfig.json",
    "content",
    "tools",
]

# Directories to include under workspace root (infrastructure layer)
INCLUDE_ROOTS_WORKSPACE = [
    ".cursor/rules/aether.mdc",
    ".github",
]

# Top-level files under aether/ (content layer)
INCLUDE_TOP_LEVEL = [
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "PROJECT-MAP.md",
    "ROADMAP.md",
    "STRATEGY.md",
]

# Top-level files under workspace root (infrastructure)
INCLUDE_TOP_LEVEL_WORKSPACE = [
    "LICENSE",
    ".gitignore",
    "AGENTS.md",                                             # root pointer (thin)
    "README.md",                                             # root pointer (thin)
]

# Exclude patterns (matched against relative path)
EXCLUDE_PATTERNS = [
    "node_modules",
    "__pycache__",
    ".astro/",
    "site/dist",
    "site/node_modules",
    ".pytest_cache",
    ".mypy_cache",
    "labs/snapshots",
    "labs/integrity",
    ".aether-persona",
    "gen6-noesis/archive",          # 大量归档数据,单独处理
    "gen6-noesis/collapse-events",   # 隐私
    "gen6-noesis/critique",
    "gen6-noesis/evolution-proposals",
    "gen6-noesis/code-grades",
    "gen5-ecoware/nursery",
    "gen5-ecoware/species-registry.json",
]


def is_excluded(rel_path: str) -> bool:
    return any(pat in rel_path for pat in EXCLUDE_PATTERNS)


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except OSError as e:
        return f"ERROR:{e}"


def scan_tree() -> dict[str, dict]:
    """Return {relative_path: {size, hash, mtime}}.

    Paths under workspace-root (LICENSE, .cursor/, .github/, root-level pointers)
    are recorded with a ``workspace:`` prefix so they don't collide with
    aether/-relative paths that happen to share a suffix.
    """
    result: dict[str, dict] = {}

    def walk(p: Path, base: Path, prefix: str = ""):
        if not p.exists():
            return
        if p.is_file():
            rel = str(p.relative_to(base)).replace("\\", "/")
            tag = prefix + rel
            if is_excluded(rel):
                return
            try:
                stat = p.stat()
                result[tag] = {
                    "size": stat.st_size,
                    "sha256": sha256_of_file(p),
                    "mtime": int(stat.st_mtime),
                }
            except OSError:
                pass
        elif p.is_dir():
            rel = str(p.relative_to(base)).replace("\\", "/")
            if is_excluded(rel):
                return
            try:
                for child in p.iterdir():
                    walk(child, base, prefix)
            except PermissionError:
                pass

    for name in INCLUDE_TOP_LEVEL:
        walk(ROOT / name, ROOT)
    for rel in INCLUDE_ROOTS:
        walk(ROOT / rel, ROOT)
    for name in INCLUDE_TOP_LEVEL_WORKSPACE:
        walk(WORKSPACE_ROOT / name, WORKSPACE_ROOT, prefix="workspace:")
    for rel in INCLUDE_ROOTS_WORKSPACE:
        walk(WORKSPACE_ROOT / rel, WORKSPACE_ROOT, prefix="workspace:")

    return result


def diff(baseline: dict, current: dict) -> dict:
    b_keys = set(baseline.keys())
    c_keys = set(current.keys())
    added = sorted(c_keys - b_keys)
    deleted = sorted(b_keys - c_keys)
    modified = []
    unchanged = []
    for k in sorted(b_keys & c_keys):
        if baseline[k].get("sha256") != current[k].get("sha256"):
            modified.append(k)
        else:
            unchanged.append(k)
    return {"added": added, "deleted": deleted, "modified": modified, "unchanged": unchanged}


def render_report(d: dict, total: int, verbose: bool = False) -> str:
    lines = []
    lines.append(f"Integrity scan · {total} files tracked")
    lines.append("")
    if d["deleted"]:
        lines.append(f"🔴 DELETED ({len(d['deleted'])})  — 这些文件不见了:")
        for p in d["deleted"]:
            lines.append(f"   - {p}")
        lines.append("")
    else:
        lines.append("✅ No deletions")
        lines.append("")

    if d["added"]:
        lines.append(f"🟢 ADDED ({len(d['added'])})")
        for p in d["added"][:20]:
            lines.append(f"   + {p}")
        if len(d["added"]) > 20:
            lines.append(f"   … and {len(d['added']) - 20} more")
        lines.append("")

    if d["modified"]:
        lines.append(f"🟡 MODIFIED ({len(d['modified'])})")
        for p in d["modified"][:20]:
            lines.append(f"   ~ {p}")
        if len(d["modified"]) > 20:
            lines.append(f"   … and {len(d['modified']) - 20} more")
        lines.append("")

    lines.append(f"✓ UNCHANGED: {len(d['unchanged'])} files")
    if verbose:
        for p in d["unchanged"]:
            lines.append(f"   · {p}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether integrity checker.")
    ap.add_argument("--save-baseline", action="store_true",
                    help="overwrite baseline.json with current state")
    ap.add_argument("--json", action="store_true",
                    help="output diff JSON only")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    print("→ scanning tracked files...", file=sys.stderr)
    current = scan_tree()
    total_files = len(current)
    total_bytes = sum(m["size"] for m in current.values())

    now = datetime.now(timezone.utc)
    snapshot = {
        "generated_at": now.isoformat(),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "files": current,
    }

    # Day 11 (coll-0083 Tier-3): only write LATEST / history when state
    # actually changed · previously every invocation appended one file
    # to history/ forever · SSD churn + git noise · zero signal.
    prev_files: dict = {}
    if LATEST_PATH.exists():
        try:
            prev_files = json.loads(LATEST_PATH.read_text(encoding="utf-8-sig")).get("files") or {}
        except (json.JSONDecodeError, OSError):
            prev_files = {}
    state_changed = prev_files != current

    hist_path: Optional[Path] = None
    if state_changed:
        LATEST_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        hist_path = HISTORY_DIR / f"{now.strftime('%Y-%m-%dT%H%M%SZ')}.json"
        hist_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        _prune_history(HISTORY_DIR, keep_latest=50)

    # Load baseline
    if BASELINE_PATH.exists():
        try:
            baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8-sig"))["files"]
        except (json.JSONDecodeError, KeyError, OSError):
            baseline = {}
    else:
        baseline = {}

    d = diff(baseline, current)

    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print(render_report(d, total_files, verbose=args.verbose))
        print(f"\nTotal size: {total_bytes / 1024:.1f} KB")
        if state_changed:
            print(f"Latest scan: {LATEST_PATH.relative_to(ROOT)}")
            if hist_path is not None:
                print(f"History: {hist_path.relative_to(ROOT)}")
        else:
            print("Latest scan: (unchanged · no new snapshot written)")

    if args.save_baseline:
        BASELINE_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✓ baseline updated: {BASELINE_PATH.relative_to(ROOT)}", file=sys.stderr)

    # Exit code: non-zero if there are deletions (alert condition)
    return 1 if d["deleted"] else 0


if __name__ == "__main__":
    sys.exit(main())
