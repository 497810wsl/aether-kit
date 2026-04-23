#!/usr/bin/env python3
"""
aether_calibrate.py — 场浓度自校准器

读最近 N 个坍缩(gen6-noesis/collapse-events/coll-*.md),统计每个场的
激活频率、用户反应,产出:
- 浓度漂移建议(哪些场应该默认拉高/降低)
- 新场孕育候选(频繁同现但没有已定义场覆盖的场组合)

用法:
    python bin/aether_calibrate.py               # 分析最近 20 次
    python bin/aether_calibrate.py --last 50
    python bin/aether_calibrate.py --dry-run     # 不写文件,只打印

产出:
    gen6-noesis/mirror/preference-calibration.md  (覆盖写)
    gen5-ecoware/nursery/*.seed.md                (若发现新物种候选,追加)
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COLL_DIR = ROOT / "gen6-noesis" / "collapse-events"
OUT_PATH = ROOT / "gen6-noesis" / "mirror" / "preference-calibration.md"
NURSERY = ROOT / "gen5-ecoware" / "nursery"

REACTION_WEIGHTS = {
    "positive": 1.0,
    "accepted": 1.0,
    "produced": 0.3,
    "pending": 0.3,
    "neutral": 0.0,
    "pending-blind-review": 0.0,
    "mixed": -0.3,
    "negative": -1.0,
    "rejected": -1.0,
}


@dataclass
class Collapse:
    path: Path
    fields: dict[str, float]
    reaction: str = "neutral"
    source: str = ""
    timestamp: str = ""


def parse_coll(path: Path) -> Collapse | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL | re.MULTILINE)
    if not m:
        return None
    frontmatter = m.group(1)

    fields: dict[str, float] = {}
    fm_match = re.search(r"active_fields:\s*\n((?:\s{2,}[\w-]+:\s*-?[\d.]+\s*\n)+)", frontmatter)
    if fm_match:
        for line in fm_match.group(1).strip().splitlines():
            fm = re.match(r"\s*([\w-]+):\s*(-?[\d.]+)", line)
            if fm:
                fields[fm.group(1)] = float(fm.group(2))

    # v2: reaction field tolerates prose — normalize fuzzy forms to canonical keys.
    # Real coll files often write `reaction: positive (user ...)` or `pending-blind-review`.
    reaction = "neutral"
    r_match = re.search(r"reaction:\s*([^\n]+)", frontmatter)
    if r_match:
        raw = r_match.group(1).strip().lower()
        # Canonical mapping: take the first recognized token
        pos_words = ("positive", "accepted", "delivered", "adopted", "shipped")
        neg_words = ("negative", "rejected", "mixed", "failed", "reverted")
        neutral_words = ("pending", "produced", "silent", "neutral", "awaiting", "n/a")
        if any(w in raw for w in pos_words):
            reaction = "positive"
        elif any(w in raw for w in neg_words):
            reaction = "negative"
        elif any(w in raw for w in neutral_words):
            reaction = "neutral"
        else:
            reaction = "neutral"

    source = ""
    s_match = re.search(r"source:\s*(.+)", frontmatter)
    if s_match:
        source = s_match.group(1).strip()

    timestamp = ""
    t_match = re.search(r"at:\s*([\d\-T:+.Z]+)", frontmatter)
    if t_match:
        timestamp = t_match.group(1).strip()

    return Collapse(path=path, fields=fields, reaction=reaction, source=source, timestamp=timestamp)


def load_recent(limit: int) -> list[Collapse]:
    if not COLL_DIR.exists():
        return []
    files = sorted(COLL_DIR.glob("coll-*.md"), reverse=True)[:limit]
    out = []
    for p in files:
        c = parse_coll(p)
        if c and c.fields:
            out.append(c)
    return out


def field_stats(collapses: list[Collapse]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "total_concentration": 0.0,
        "reaction_weighted": 0.0,
        "values": [],
    })
    for c in collapses:
        weight = REACTION_WEIGHTS.get(c.reaction, 0.0)
        for name, conc in c.fields.items():
            s = stats[name]
            s["count"] += 1
            s["total_concentration"] += conc
            s["reaction_weighted"] += conc * weight
            s["values"].append(conc)

    result = {}
    for name, s in stats.items():
        avg = s["total_concentration"] / max(s["count"], 1)
        acceptance = s["reaction_weighted"] / max(s["count"], 1)
        result[name] = {
            "count": s["count"],
            "avg_concentration": round(avg, 3),
            "acceptance_score": round(acceptance, 3),
            "suggested_default": round(max(0.0, min(1.0, avg + acceptance * 0.1)), 2),
        }
    return result


def cooccurrence(collapses: list[Collapse]) -> Counter:
    counts = Counter()
    for c in collapses:
        names = sorted(c.fields.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                counts[(names[i], names[j])] += 1
    return counts


def detect_seeds(collapses: list[Collapse], min_occurrence: int = 3) -> list[tuple[str, str, int]]:
    co = cooccurrence(collapses)
    return [(a, b, n) for (a, b), n in co.items() if n >= min_occurrence]


def render_report(stats: dict, co_seeds: list, n_collapses: int) -> str:
    lines = []
    lines.append("# Field Calibration Report")
    lines.append("")
    lines.append(f"> Auto-generated by `bin/aether_calibrate.py` at "
                 f"{datetime.now(timezone.utc).isoformat()}")
    lines.append(f"> Based on the most recent **{n_collapses}** collapses.")
    lines.append("")
    lines.append("## Per-field statistics")
    lines.append("")
    lines.append("| field | count | avg conc | acceptance | suggested default |")
    lines.append("|---|---:|---:|---:|---:|")
    for name, s in sorted(stats.items(), key=lambda x: -x[1]["count"]):
        lines.append(
            f"| `{name}` | {s['count']} | {s['avg_concentration']} | "
            f"{s['acceptance_score']:+.2f} | **{s['suggested_default']}** |"
        )
    lines.append("")
    lines.append("_acceptance score_: weighted by `reaction` frontmatter field. "
                 "`+1` is strong positive, `-1` is strong negative.")
    lines.append("")
    lines.append("## Co-occurrence seeds (potential new species)")
    lines.append("")
    if not co_seeds:
        lines.append("_No field-pair co-occurred ≥ 3 times yet. Observing._")
    else:
        lines.append("| field A | field B | co-occurrence |")
        lines.append("|---|---|---:|")
        for a, b, n in sorted(co_seeds, key=lambda x: -x[2]):
            lines.append(f"| `{a}` | `{b}` | {n} |")
        lines.append("")
        lines.append("_Pairs with count ≥ 3 become species nursery candidates "
                     "(`gen5-ecoware/nursery/`)._")
    lines.append("")
    lines.append("## How to apply")
    lines.append("")
    lines.append("The `suggested default` column tells the trigger system (`triggers.md`) "
                 "what concentration to use when this field is soft-triggered. ")
    lines.append("Orchestrator should update `gen4-morphogen/composers/triggers.md` "
                 "every 50 collapses using this report.")
    lines.append("")
    return "\n".join(lines)


def emerge_seeds(co_seeds: list[tuple[str, str, int]], existing_species: set[str]) -> list[Path]:
    NURSERY.mkdir(parents=True, exist_ok=True)
    created = []
    for a, b, n in co_seeds:
        sig = f"{a}+{b}"
        seed_name = f"seed-{a}-{b}"
        seed_path = NURSERY / f"{seed_name}.seed.md"
        if seed_path.exists() or sig in existing_species:
            continue
        content = f"""---
seed_id: {seed_name}
emerged_at: {datetime.now(timezone.utc).isoformat()}
source: aether_calibrate.py
co_occurrence_count: {n}
fields: [{a}, {b}]
proposed_niche: consumer
observations_remaining: {max(0, 5 - n)}
status: {"ripe-for-promotion" if n >= 5 else "ripening"}
---

# {seed_name}

## Emergence evidence

These two fields co-occurred in **{n}** recent collapses without being
covered by any existing species.

## Proposed niche

consumer — metabolizes `{a}` and `{b}` into composite outputs.

## Observation window

{"Ready for promotion to species." if n >= 5 else f"Need {5 - n} more matching collapses."}

*auto-emerged · do not edit manually · let evolution handle it*
"""
        seed_path.write_text(content, encoding="utf-8")
        created.append(seed_path)
    return created


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether field calibration report generator.")
    ap.add_argument("--last", type=int, default=20, help="analyze last N collapses (default 20)")
    ap.add_argument("--dry-run", action="store_true", help="do not write files")
    args = ap.parse_args()

    collapses = load_recent(args.last)
    if not collapses:
        print("no collapses found under", COLL_DIR, file=sys.stderr)
        return 1

    stats = field_stats(collapses)
    co_seeds = detect_seeds(collapses, min_occurrence=3)
    report = render_report(stats, co_seeds, len(collapses))

    if args.dry_run:
        print(report)
        if co_seeds:
            print("\n(dry-run) would emerge:",
                  [f"seed-{a}-{b}" for a, b, _ in co_seeds])
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"wrote {OUT_PATH}")

    created = emerge_seeds(co_seeds, set())
    for p in created:
        print(f"emerged seed: {p.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
