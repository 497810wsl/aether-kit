#!/usr/bin/env python3
"""
aether_archive.py — Layer 1 Memory · 冷热分离

把 gen6-noesis/collapse-events/ 下的 coll-*.md 按年龄分层:
- **热层** (hot): 最近 N 个(默认 100)保留在原位置,AI 默认读
- **冷层** (cold): 更老的按季度归档到 gen6-noesis/archive/<YYYY-Qn>/
- **索引** (index): archive/index.json 记录所有归档 coll 的元数据,供 recall 快速筛选

为什么要做:coll 堆到 500+ 会让 AI 加载变慢,critic/calibrate 跑一次从秒级变分钟级。
分层后,AI 默认只看 100 个热,偶尔从 archive 按需拉冷。

用法:
    python bin/aether_archive.py                    # 预览归档计划(dry-run)
    python bin/aether_archive.py --apply            # 真正执行归档
    python bin/aether_archive.py --hot 50 --apply   # 自定义热层大小
    python bin/aether_archive.py --rebuild-index    # 不归档,只重建索引
    python bin/aether_archive.py --list             # 列出当前热/冷分布

设计原则:
- 零依赖(Python stdlib)
- append-only(已归档的 coll 不删,只加)
- idempotent(重复跑无副作用)
- safe(默认 dry-run,必须 --apply 才动)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COLL_DIR = ROOT / "gen6-noesis" / "collapse-events"
ARCHIVE_DIR = ROOT / "gen6-noesis" / "archive"
INDEX_PATH = ARCHIVE_DIR / "index.json"

DEFAULT_HOT_SIZE = 100


@dataclass
class CollMeta:
    coll_id: str
    path: str  # relative to ROOT
    at: str  # ISO timestamp
    source: str
    reaction: str
    fields: dict[str, float] = field(default_factory=dict)
    quarter: str = ""  # e.g. 2026-Q2
    age_days: int = 0
    layer: str = "hot"  # hot | cold


def parse_coll_meta(path: Path) -> CollMeta | None:
    """Extract metadata from coll-XXXX.md frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm:
        return None
    frontmatter = fm.group(1)

    coll_id_m = re.search(r"collapse_id:\s*(\S+)", frontmatter)
    at_m = re.search(r"at:\s*([^\n]+)", frontmatter)
    source_m = re.search(r"source:\s*([^\n]+)", frontmatter)
    reaction_m = re.search(r"reaction:\s*([^\n]+)", frontmatter)

    fields_dict: dict[str, float] = {}
    fields_m = re.search(r"active_fields:\s*\n((?:\s{2,}[\w-]+:\s*-?[\d.]+[^\n]*\n)+)", frontmatter)
    if fields_m:
        for line in fields_m.group(1).strip().splitlines():
            m = re.match(r"\s*([\w-]+):\s*(-?[\d.]+)", line)
            if m:
                fields_dict[m.group(1)] = float(m.group(2))

    coll_id = coll_id_m.group(1).strip() if coll_id_m else path.stem
    at_raw = at_m.group(1).strip() if at_m else ""

    # Parse timestamp
    age_days = 0
    quarter = "unknown"
    try:
        # Handle ISO variants including ones with "+00:00" or "Z"
        at_norm = at_raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(at_norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - dt).days
        q = (dt.month - 1) // 3 + 1
        quarter = f"{dt.year}-Q{q}"
    except (ValueError, IndexError):
        pass

    return CollMeta(
        coll_id=coll_id,
        path=str(path.relative_to(ROOT)).replace("\\", "/"),
        at=at_raw,
        source=(source_m.group(1).strip() if source_m else "")[:120],
        reaction=(reaction_m.group(1).strip() if reaction_m else "neutral")[:80],
        fields=fields_dict,
        quarter=quarter,
        age_days=age_days,
    )


def scan_all_colls() -> list[CollMeta]:
    """Find all coll-*.md in both active and archive locations."""
    metas: list[CollMeta] = []

    # Active (hot) location
    if COLL_DIR.exists():
        for p in sorted(COLL_DIR.glob("coll-*.md")):
            m = parse_coll_meta(p)
            if m:
                m.layer = "hot"
                metas.append(m)

    # Archive (cold) location
    if ARCHIVE_DIR.exists():
        for qdir in sorted(ARCHIVE_DIR.iterdir()):
            if not qdir.is_dir() or not re.match(r"\d{4}-Q[1-4]", qdir.name):
                continue
            for p in sorted(qdir.glob("coll-*.md")):
                m = parse_coll_meta(p)
                if m:
                    m.layer = "cold"
                    metas.append(m)
    return metas


def classify(metas: list[CollMeta], hot_size: int) -> tuple[list[CollMeta], list[CollMeta]]:
    """Return (keep_hot, move_to_cold) based on reverse chronological order."""
    # Sort by id descending (newest first) — coll ids monotonically increase
    sorted_metas = sorted(metas, key=lambda m: m.coll_id, reverse=True)
    keep_hot = sorted_metas[:hot_size]
    should_be_cold = sorted_metas[hot_size:]
    # Filter: only the ones currently in "hot" layer need to move
    to_move = [m for m in should_be_cold if m.layer == "hot"]
    return keep_hot, to_move


def execute_archive(to_move: list[CollMeta], apply: bool) -> list[str]:
    """Move coll files from hot to their quarter directory. Returns log lines."""
    log = []
    for m in to_move:
        src = ROOT / m.path
        if not src.exists():
            log.append(f"skip (missing): {m.path}")
            continue
        dest_dir = ARCHIVE_DIR / m.quarter
        dest = dest_dir / src.name
        if dest.exists():
            log.append(f"skip (already archived): {dest.relative_to(ROOT)}")
            continue
        if apply:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            # Update the meta to reflect new path
            m.path = str(dest.relative_to(ROOT)).replace("\\", "/")
            m.layer = "cold"
            log.append(f"moved: {src.relative_to(ROOT)} → {dest.relative_to(ROOT)}")
        else:
            log.append(f"would move: {src.relative_to(ROOT)} → {dest.relative_to(ROOT)}")
    return log


def build_index(metas: list[CollMeta]) -> dict[str, Any]:
    """Build the master index written to archive/index.json."""
    metas_sorted = sorted(metas, key=lambda m: m.coll_id)
    # Stats
    total = len(metas_sorted)
    hot_count = sum(1 for m in metas_sorted if m.layer == "hot")
    cold_count = total - hot_count
    quarters = sorted({m.quarter for m in metas_sorted if m.quarter != "unknown"})

    # Field activation frequency across ALL colls
    from collections import Counter
    field_counter: Counter[str] = Counter()
    reaction_counter: Counter[str] = Counter()
    for m in metas_sorted:
        for name in m.fields:
            field_counter[name] += 1
        # Normalize reaction first token
        reaction_counter[m.reaction.split()[0] if m.reaction else "neutral"] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_collapses": total,
        "hot_count": hot_count,
        "cold_count": cold_count,
        "quarters": quarters,
        "field_activation_all_time": dict(field_counter.most_common(30)),
        "reaction_distribution": dict(reaction_counter),
        "entries": [asdict(m) for m in metas_sorted],
    }


def cmd_list(args, metas: list[CollMeta]) -> None:
    print(f"total colls: {len(metas)}")
    hot = [m for m in metas if m.layer == "hot"]
    cold = [m for m in metas if m.layer == "cold"]
    print(f"  hot: {len(hot)} (in {COLL_DIR.relative_to(ROOT)})")
    print(f"  cold: {len(cold)} (in {ARCHIVE_DIR.relative_to(ROOT)})")
    if cold:
        from collections import Counter
        by_q = Counter(m.quarter for m in cold)
        for q, c in sorted(by_q.items()):
            print(f"    {q}: {c}")
    if hot:
        oldest = max(hot, key=lambda m: m.age_days)
        newest = min(hot, key=lambda m: m.age_days)
        print(f"  hot layer age span: {newest.age_days}d (newest) ~ {oldest.age_days}d (oldest)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether Layer-1 memory archive tool.")
    ap.add_argument("--hot", type=int, default=DEFAULT_HOT_SIZE,
                    help=f"how many recent colls stay hot (default {DEFAULT_HOT_SIZE})")
    ap.add_argument("--apply", action="store_true",
                    help="actually move files (default is dry-run)")
    ap.add_argument("--rebuild-index", action="store_true",
                    help="only rebuild archive/index.json, do not move anything")
    ap.add_argument("--list", action="store_true",
                    help="show current hot/cold distribution and exit")
    args = ap.parse_args()

    metas = scan_all_colls()
    if not metas:
        print(f"no colls found in {COLL_DIR.relative_to(ROOT)}", file=sys.stderr)
        return 1

    if args.list:
        cmd_list(args, metas)
        return 0

    if args.rebuild_index:
        index = build_index(metas)
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"rebuilt {INDEX_PATH.relative_to(ROOT)} · {index['total_collapses']} entries")
        return 0

    _keep_hot, to_move = classify(metas, args.hot)

    print(f"total: {len(metas)}  ·  hot limit: {args.hot}  ·  to archive: {len(to_move)}")
    if not to_move:
        print(f"nothing to archive. heat layer already fits within {args.hot}.")
        # Still refresh index
        if args.apply:
            index = build_index(metas)
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"refreshed index: {INDEX_PATH.relative_to(ROOT)}")
        return 0

    print()
    log = execute_archive(to_move, apply=args.apply)
    for line in log:
        print("  " + line)
    print()

    if args.apply:
        # After applying, re-scan to get updated paths, then build index
        metas_final = scan_all_colls()
        index = build_index(metas_final)
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {INDEX_PATH.relative_to(ROOT)} · {index['total_collapses']} entries total")
        print(f"hot layer: {index['hot_count']}  ·  cold layer: {index['cold_count']}")
    else:
        print("(dry-run) use --apply to actually move files.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
