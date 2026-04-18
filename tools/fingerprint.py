"""Offline field-fingerprint analysis of hero-variant-*.html files.
Run: python tools/fingerprint.py
"""
import json
import os
import re
import sys

DOCS = "docs"
VARIANTS = {
    "linus": "hero-variant-linus.html",
    "ive":   "hero-variant-ive.html",
    "nolan": "hero-variant-nolan.html",
}
KEYWORDS = {
    "linus": ["hedge", "catastrophic", "fix", "kill", "delete", "bugs",
              "injection", "ship", "first", "wrong", "break", "cost"],
    "ive":   ["落下", "含糊", "场", "纸", "培育", "共同", "restraint",
              "material", "craft", "paper", "brass", "anno", "慢", "克制"],
    "nolan": ["timeline", "between", "fold", "collapse", "before", "after",
              "t+", "t-", "t−", "vault", "remember", "gravity", "loop"],
}


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def analyze(path):
    text = open(path, "r", encoding="utf-8").read()
    body_text = text.lower()
    colors = sorted(set(c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,8}\b", text)))
    fonts = re.findall(r"font-family:\s*([^;]+);", text)
    first_font = "?"
    if fonts:
        raw = fonts[0].split(",")[0].strip()
        first_font = raw.strip('"').strip("'").strip()
    grid_cols = re.findall(r"grid-template-columns:\s*([^;]+);", text)
    multi_col = sum(1 for c in grid_cols if c.count("fr") >= 2 or "1fr" in c and "auto" in c)
    hits = {k: [w for w in ws if w.lower() in body_text] for k, ws in KEYWORDS.items()}
    return {
        "bytes": len(text),
        "nodes_approx": text.count("<"),
        "colors_unique": len(colors),
        "colors_sample": colors[:6],
        "primary_font": first_font,
        "font_family_variants": len(set(f.split(",")[0].strip() for f in fonts)),
        "multi_col_grids": multi_col,
        "total_grids": len(grid_cols),
        "hits_linus_kw": len(hits["linus"]),
        "hits_ive_kw": len(hits["ive"]),
        "hits_nolan_kw": len(hits["nolan"]),
        "own_field_hits": [],
    }


def main():
    data = {}
    for v, f in VARIANTS.items():
        path = os.path.join(DOCS, f)
        if not os.path.exists(path):
            print(f"[missing] {path}", file=sys.stderr)
            continue
        data[v] = analyze(path)
        data[v]["own_field_hits"] = [
            w for w in KEYWORDS[v]
            if w.lower() in open(path, "r", encoding="utf-8").read().lower()
        ]

    # Overlap analysis
    variants = list(data.keys())
    overlap = {}
    for i, a in enumerate(variants):
        for b in variants[i+1:]:
            key = f"{a}↔{b}"
            overlap[key] = {
                "color_jaccard": round(jaccard(data[a]["colors_sample"], data[b]["colors_sample"]), 3),
                "font_same": data[a]["primary_font"] == data[b]["primary_font"],
            }

    summary = {
        "variants": data,
        "overlap": overlap,
        "verdict": verdict(data, overlap),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def verdict(data, overlap):
    if len(data) < 2:
        return "insufficient-data"
    avg_color_overlap = sum(o["color_jaccard"] for o in overlap.values()) / max(len(overlap), 1)
    fonts = set(d["primary_font"] for d in data.values())
    match_rates = [len(data[v]["own_field_hits"]) / max(len(KEYWORDS[v]), 1) for v in data]
    avg_match = sum(match_rates) / len(match_rates)
    sizes = [d["bytes"] for d in data.values()]
    spread = max(sizes) / max(min(sizes), 1)
    flag = "pass" if (avg_color_overlap < 0.1 and len(fonts) == len(data) and avg_match > 0.3) \
        else "warn" if (avg_color_overlap < 0.25 and avg_match > 0.15) else "fail"
    return {
        "level": flag,
        "avg_color_overlap": round(avg_color_overlap, 3),
        "font_families_distinct": f"{len(fonts)}/{len(data)}",
        "avg_own_field_match": round(avg_match, 3),
        "byte_size_spread_x": round(spread, 2),
    }


if __name__ == "__main__":
    main()
