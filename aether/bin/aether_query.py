#!/usr/bin/env python3
"""
aether_query.py — Layer B (SQLite) 查询入口 · Owner / AI 共用

Use cases:
  aether_query "Owner 讨厌什么"          # FTS5 全文搜
  aether_query --field engineering-rigor # 场的使用画像
  aether_query --species engineering-rigor-linus-torvalds
  aether_query --coll coll-0069          # 特定 coll
  aether_query --session <session_id>    # 一个会话的事件流
  aether_query --stats                   # 全局概览(等同 indexer stats)
  aether_query --list decisions          # 所有决策类记忆
  aether_query --drift                   # mirror 与最近 coll 的脱节度

Output: plain text · human-readable · stable format(可被 shell 管道处理)

Principles:
  1. Read-only · 绝不改 DB / markdown
  2. 0 external deps · sqlite3 stdlib
  3. fail-loud on bad query · fail-soft on missing data
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from aether_paths import (
    CENTRAL_OVERLAY,
    CENTRAL_ROOT,
    activate_overlay_for_cli,
    add_path_arg,
)

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = CENTRAL_ROOT                   # back-compat alias

# Day 13 · overlay-aware · PATH-RESOLUTION-SPEC §3.1
# DB_PATH is reassigned in main() after activate_overlay_for_cli().
DB_PATH: Path = CENTRAL_OVERLAY / "index.db"


def connect_ro() -> sqlite3.Connection:
    if not DB_PATH.exists():
        # Honest error message tells user exactly which overlay is missing
        # its index.db · and how to build it. Guest projects may need their
        # own ingest pass before queries work.
        print(
            f"(no index at {DB_PATH} · "
            f"run `python bin/aether_indexer.py ingest --path {DB_PATH.parent.parent}` first)",
            file=sys.stderr,
        )
        sys.exit(2)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fts_escape(q: str) -> str:
    """Escape a raw user query for FTS5. Prefer phrase search when words > 1."""
    q = q.strip()
    if not q:
        return '""'
    if re.search(r'[\s\u3000]', q):
        safe = q.replace('"', '""')
        return f'"{safe}"'
    return q.replace('"', '""')


def fmt_memory_row(r: sqlite3.Row, max_content: int = 240) -> str:
    content = r["content"] or ""
    content = re.sub(r"\s+", " ", content).strip()
    if len(content) > max_content:
        content = content[:max_content] + "..."
    imp = r["importance"]
    cat = r["category"] or "?"
    src = r["source_ref"] or r["source_type"] or "?"
    return f"  imp={imp:.2f} [{cat:10s}] {src:30s}\n    {content}"


def _is_fts_friendly(q: str) -> bool:
    """trigram tokenizer needs >= 3 char matches. Short CJK queries
    (>= 3 chars of latin ASCII too) go through FTS5. Anything 1-2 chars
    of CJK must LIKE-fallback."""
    q = q.strip()
    non_space = re.sub(r"\s+", "", q)
    return len(non_space) >= 3


def do_search(query: str, top_k: int = 5, category: str | None = None) -> int:
    conn = connect_ro()
    fts_mode = _is_fts_friendly(query)

    if fts_mode:
        fts_q = fts_escape(query)
        where = "memories_fts MATCH ?"
        params: list = [fts_q]
        if category:
            where += " AND m.category = ?"
            params.append(category)
        try:
            rows = conn.execute(
                f"""
                SELECT m.id, m.category, m.importance, m.content, m.summary,
                       m.source_ref, m.source_type,
                       bm25(memories_fts) AS rank
                FROM memories_fts
                JOIN memories m ON m.id = memories_fts.mem_id
                WHERE {where}
                ORDER BY rank ASC, m.importance DESC
                LIMIT ?
                """,
                (*params, top_k),
            ).fetchall()
        except sqlite3.OperationalError as e:
            print(f"FTS query error: {e} · falling back to LIKE", file=sys.stderr)
            fts_mode = False
    else:
        rows = []

    if not fts_mode or not rows:
        like_q = f"%{query.strip()}%"
        params = [like_q, like_q]
        where = "(content LIKE ? OR summary LIKE ?)"
        if category:
            where += " AND category = ?"
            params.append(category)
        rows = conn.execute(
            f"""
            SELECT id, category, importance, content, summary,
                   source_ref, source_type
            FROM memories
            WHERE {where}
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
            """,
            (*params, top_k),
        ).fetchall()

    if not rows:
        print(f"(no matches for: {query})")
        return 0

    mode = "FTS5" if fts_mode else "LIKE"
    print(f"[{len(rows)} matches for: {query!r} · mode={mode}]\n")
    for r in rows:
        print(fmt_memory_row(r))
        print()
    return 0


def do_field(field_id: str) -> int:
    conn = connect_ro()
    row = conn.execute(
        "SELECT * FROM fields_usage WHERE field_id = ?", (field_id,)
    ).fetchone()
    if not row:
        print(f"(no field: {field_id})")
        return 1

    n = row["activation_count"] or 0
    pos = row["positive_count"] or 0
    neg = row["negative_count"] or 0
    sil = row["silent_count"] or 0
    avg = row["avg_concentration"] or 0
    print(f"field · {field_id}")
    print(f"  activations:     {n}")
    print(f"  avg concentration: {avg:.2f}")
    print(f"  reactions:       +{pos}  -{neg}  ?{sil}")
    print(f"  last activated:  {row['last_activated_at'] or '(never)'}")

    print()
    print("  recent colls using this field:")
    rows = conn.execute(
        "SELECT coll_id, created_at, semantic, fields_json FROM colls "
        "WHERE fields_json LIKE ? ORDER BY coll_id DESC LIMIT 5",
        (f'%"{field_id}"%',),
    ).fetchall()
    for r in rows:
        try:
            fd = json.loads(r["fields_json"] or "{}")
            val = fd.get(field_id, 0)
        except Exception:
            val = 0
        sem = r["semantic"] or ""
        sem = re.sub(r"\s+", " ", sem)[:100]
        print(f"    {r['coll_id']} [{val:+.2f}] {sem}")
    return 0


def do_species(species_id: str) -> int:
    conn = connect_ro()
    reg = conn.execute(
        "SELECT * FROM species_registry WHERE species_id = ?", (species_id,)
    ).fetchone()
    if reg:
        print(f"species · {species_id}")
        print(f"  niche:         {reg['niche'] or '?'}")
        print(f"  health:        {reg['health'] or '?'}")
        print(f"  is_nursery:    {bool(reg['is_nursery'])}")
        if reg["core_vector"]:
            print(f"  core_vector:   {reg['core_vector']}")
    else:
        print(f"species · {species_id} (not in registry)")

    print()
    rows = conn.execute(
        "SELECT fired_at, coll_ref, reaction FROM species_activations "
        "WHERE species_id = ? ORDER BY fired_at DESC LIMIT 20",
        (species_id,),
    ).fetchall()
    print(f"  activations (recent {len(rows)}):")
    for r in rows:
        print(f"    {str(r['fired_at'] or '')[:20]:22s} {r['coll_ref']:12s} {r['reaction'] or ''}")
    if not rows:
        print("    (none)")
    return 0


def do_coll(coll_id: str) -> int:
    conn = connect_ro()
    row = conn.execute("SELECT * FROM colls WHERE coll_id = ?", (coll_id,)).fetchone()
    if not row:
        print(f"(no coll: {coll_id})")
        return 1
    print(f"coll · {coll_id}")
    print(f"  created_at:    {row['created_at']}")
    print(f"  trigger:       {row['trigger_text']}")
    print(f"  reaction:      {row['owner_reaction'] or '?'}")
    print(f"  fields:        {row['fields_json']}")
    print(f"  species:       {row['species_json']}")
    print(f"  semantic:      {row['semantic']}")
    print(f"  source:        {row['source_path']}")
    return 0


def do_list(kind: str, limit: int = 20) -> int:
    conn = connect_ro()
    cat_map = {
        "decisions": "decision",
        "preferences": "preference",
        "identity": "identity",
        "rules": "rule",
        "experience": "experience",
    }
    cat = cat_map.get(kind, kind)
    rows = conn.execute(
        "SELECT id, category, importance, content, source_ref FROM memories "
        "WHERE category = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
        (cat, limit),
    ).fetchall()
    print(f"[{len(rows)} memories · category={cat}]\n")
    for r in rows:
        print(fmt_memory_row(r))
        print()
    return 0


def do_drift() -> int:
    """Quick drift signal · compare essence category counts with recent coll
    distribution. Replaces a chunk of what aether_critic.py does but in 0.1s."""
    conn = connect_ro()
    recent = conn.execute(
        "SELECT coll_id, species_json FROM colls ORDER BY coll_id DESC LIMIT 10"
    ).fetchall()
    species_freq: dict[str, int] = {}
    for r in recent:
        try:
            for s in json.loads(r["species_json"] or "[]"):
                species_freq[s] = species_freq.get(s, 0) + 1
        except Exception:
            continue
    registered = {
        r["species_id"] for r in
        conn.execute("SELECT species_id FROM species_registry WHERE is_nursery = 0").fetchall()
    }
    undocumented = sorted(species_freq.keys() - registered)
    print("drift signals (last 10 coll):\n")
    print(f"  species appearing:  {len(species_freq)}")
    print(f"  species registered: {len(registered)}")
    if undocumented:
        print(f"  UNDOCUMENTED SPECIES: {undocumented}")
    else:
        print("  (no undocumented species)")

    no_reaction = conn.execute(
        "SELECT COUNT(*) FROM colls WHERE coll_id IN "
        "(SELECT coll_id FROM colls ORDER BY coll_id DESC LIMIT 10) "
        "AND (owner_reaction IS NULL OR owner_reaction = '' "
        "     OR owner_reaction LIKE 'pending%' OR owner_reaction LIKE '(silent%')"
    ).fetchone()[0]
    print(f"  no_reaction (last 10): {no_reaction}")
    return 0


def do_briefing() -> int:
    """Compressed briefing for sessionStart · top memories · recent semantic.

    Intended to be piped into aether_handshake.py · keeps 'what to remember'
    compact enough to fit token budget (<2KB typically).
    """
    conn = connect_ro()
    print("## core memories (top 5 identity/decision · from index.db)\n")
    rows = conn.execute(
        "SELECT id, category, importance, summary, content FROM memories "
        "WHERE category IN ('identity', 'decision') AND importance >= 0.85 "
        "ORDER BY importance DESC, created_at DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        s = r["summary"] or (r["content"] or "")[:120]
        s = re.sub(r"\s+", " ", s).strip()
        print(f"- [{r['category']}] {s}")
    print()

    print("## recent collapses (last 3 · semantic)\n")
    rows = conn.execute(
        "SELECT coll_id, semantic FROM colls ORDER BY coll_id DESC LIMIT 3"
    ).fetchall()
    for r in rows:
        s = re.sub(r"\s+", " ", (r["semantic"] or ""))[:120]
        print(f"- {r['coll_id']} · {s}")
    print()

    print("## active species (registered · non-nursery)\n")
    rows = conn.execute(
        "SELECT species_id, activation_count FROM species_registry "
        "WHERE is_nursery = 0 ORDER BY activation_count DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(f"- {r['species_id']} · hit={r['activation_count']}")

    return 0


def _autopilot_tick() -> None:
    """Lazy-trigger guardian if the index is stale. Silent · non-blocking.

    Day 13 · passes cwd=DB_PATH's overlay so heartbeat advances the same
    overlay we're querying (not central by accident).
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from aether_autopilot import maybe_trigger_ingest
        maybe_trigger_ingest(cwd=str(DB_PATH.parent.parent))
    except Exception:
        pass


def _activate_overlay(args) -> None:
    """Reassign DB_PATH based on `--path` / cwd-walk.

    Day 13 · PATH-RESOLUTION-SPEC §3.1: query reads the index.db of the
    ACTIVE overlay. Briefing output (used by handshake) reflects the
    overlay's own memories · guest projects get guest colls in their
    briefing, not central's Aether-dev narrative.
    """
    global DB_PATH
    # announce to stderr UNLESS --briefing is set (briefing output is piped
    # into handshake context · must stay clean on stdout · banner-to-stderr
    # is fine but we still suppress to avoid any chance of leakage).
    suppress = getattr(args, "briefing", False)
    overlay, _ = activate_overlay_for_cli(args, announce=not suppress)
    DB_PATH = overlay / "index.db"


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether Layer B query CLI")
    ap.add_argument("query", nargs="?", help="free-text FTS query")
    ap.add_argument("-k", "--top", type=int, default=5, help="top-k results")
    ap.add_argument("--category", help="filter memories by category")
    ap.add_argument("--field", help="show stats for one field")
    ap.add_argument("--species", help="show activation timeline for one species")
    ap.add_argument("--coll", help="show a specific coll entry")
    ap.add_argument("--list", help="list memories by category (decisions|preferences|identity|rules|experience)")
    ap.add_argument("--drift", action="store_true", help="quick drift signal")
    ap.add_argument("--briefing", action="store_true", help="compressed briefing for sessionStart")
    add_path_arg(ap)
    args = ap.parse_args()

    _activate_overlay(args)
    _autopilot_tick()

    if args.field:
        return do_field(args.field)
    if args.species:
        return do_species(args.species)
    if args.coll:
        return do_coll(args.coll)
    if args.list:
        return do_list(args.list, limit=args.top if args.top > 5 else 20)
    if args.drift:
        return do_drift()
    if args.briefing:
        return do_briefing()

    if not args.query:
        ap.print_help()
        return 0

    return do_search(args.query, top_k=args.top, category=args.category)


if __name__ == "__main__":
    sys.exit(main())
