#!/usr/bin/env python3
"""
aether_indexer.py — Layer A → Layer B 物化索引器

Populates .aether/index.db from:
  · events.jsonl          (atomic events · from hooks)
  · coll-*.md             (Gen 6 collapse events · A-layer source of truth)
  · user-essence.md       (Gen 6 mirror)
  · species-registry.json (Gen 5 species)

Principles:
  1. Layer A never mutates · indexer is read-only on A
  2. Layer B is idempotent · re-running never creates duplicates
  3. Indexer uses file mtime + content hash to detect changes · cheap
  4. Schema v1 is forward-only · migrations via CREATE IF NOT EXISTS

Usage:
  python bin/aether_indexer.py init       # create schema (central)
  python bin/aether_indexer.py ingest     # pick up changes only
  python bin/aether_indexer.py rebuild    # nuke and rebuild from A
  python bin/aether_indexer.py stats      # what's in the DB
  python bin/aether_indexer.py ingest --path D:\\novel-project  # guest overlay

SQLite version: 3.35.5(verified · FTS5 + JSON1 available)
Python: stdlib only · sqlite3

──────────────────────────────────────────────────────────────────────
Day 13 · overlay-aware · PATH-RESOLUTION-SPEC.md §3.1

Before Day 13: `DATA_DIR = WORKSPACE_ROOT / ".aether"` was a module constant,
meaning indexer always wrote to central's index.db even when called (via
subprocess from sessionEnd hook) with a guest payload. Result: guest
projects' events.jsonl was never indexed · B-layer briefing for guest was
a stale central DB.

Day 13 fix (this file): DATA_DIR / DB_PATH / EVENTS_PATH / INGEST_STATE_PATH
are reassigned in main() via resolve_active_overlay(). Layer A sources that
are NOT per-project (essence / species / fields / gen6 colls) still read
from central — see §5 of PATH-RESOLUTION-SPEC.md for the cross-scope data
dependency table. When running on a guest overlay, we prefer overlay/coll/
for coll ingestion (so guest builds an index of its own colls), falling
back to central's gen6-noesis only when the CLI is in central scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from aether_paths import (
    CENTRAL_OVERLAY,
    CENTRAL_ROOT,
    activate_overlay_for_cli,
    add_path_arg,
)

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = CENTRAL_ROOT                   # back-compat alias

# Module-level defaults · main() reassigns after activate_overlay_for_cli().
# Keep names for any Day 1-12 in-process importer that reads them.
DATA_DIR: Path = CENTRAL_OVERLAY
DB_PATH: Path = DATA_DIR / "index.db"
EVENTS_PATH: Path = DATA_DIR / "events.jsonl"
INGEST_STATE_PATH: Path = DATA_DIR / "indexer-state.json"

# Layer A sources under the central aether/ tree · these are NOT per-project
# (cross-scope shared identity data · see PATH-RESOLUTION-SPEC §5).
ESSENCE_PATH = ROOT / "gen6-noesis" / "mirror" / "user-essence.md"
CALIBRATION_PATH = ROOT / "gen6-noesis" / "mirror" / "preference-calibration.md"
SPECIES_JSON = ROOT / "gen5-ecoware" / "species-registry.json"
NURSERY_DIR = ROOT / "gen5-ecoware" / "nursery"
FIELDS_DIR = ROOT / "gen4-morphogen" / "fields"

# Central's collapse-events dir · used as fallback only when indexer runs
# in central scope. Guest overlays get their own overlay/coll/ ingested.
CENTRAL_COLL_DIR = ROOT / "gen6-noesis" / "collapse-events"
# Overridden in main() to point at overlay/coll/ in guest mode.
COLL_DIR: Path = CENTRAL_COLL_DIR


SCHEMA = r"""
CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  type        TEXT NOT NULL,
  session_id  TEXT,
  tool        TEXT,
  payload     TEXT,
  source      TEXT DEFAULT 'events.jsonl'
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);

CREATE TABLE IF NOT EXISTS memories (
  id          TEXT PRIMARY KEY,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  category    TEXT NOT NULL,
  importance  REAL DEFAULT 0.5,
  content     TEXT NOT NULL,
  summary     TEXT,
  source_type TEXT,
  source_ref  TEXT,
  tags        TEXT,
  confidence  REAL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source_ref);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  mem_id UNINDEXED,
  category UNINDEXED,
  content,
  summary,
  tags,
  tokenize='trigram'
);

CREATE TABLE IF NOT EXISTS colls (
  coll_id       TEXT PRIMARY KEY,
  created_at    TEXT NOT NULL,
  semantic      TEXT,
  trigger_text  TEXT,
  fields_json   TEXT,
  species_json  TEXT,
  owner_reaction TEXT,
  source_path   TEXT,
  content_hash  TEXT,
  indexed_at    TEXT
);

CREATE TABLE IF NOT EXISTS fields_usage (
  field_id         TEXT PRIMARY KEY,
  activation_count INTEGER DEFAULT 0,
  last_activated_at TEXT,
  avg_concentration REAL,
  positive_count   INTEGER DEFAULT 0,
  negative_count   INTEGER DEFAULT 0,
  silent_count     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS species_activations (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  species_id TEXT NOT NULL,
  fired_at   TEXT NOT NULL,
  coll_ref   TEXT,
  fields_snapshot TEXT,
  reaction   TEXT
);
CREATE INDEX IF NOT EXISTS idx_species_act_species ON species_activations(species_id);
CREATE INDEX IF NOT EXISTS idx_species_act_fired ON species_activations(fired_at);

CREATE TABLE IF NOT EXISTS species_registry (
  species_id       TEXT PRIMARY KEY,
  niche            TEXT,
  born_at          TEXT,
  emerged_at       TEXT,
  core_vector      TEXT,
  health           TEXT,
  activation_count INTEGER,
  last_activated_at TEXT,
  origin           TEXT,
  is_nursery       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS files_meta (
  path        TEXT PRIMARY KEY,
  mtime       REAL,
  content_hash TEXT,
  indexed_at  TEXT
);

CREATE TABLE IF NOT EXISTS digests (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  kind        TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  period_start TEXT,
  period_end  TEXT,
  content     TEXT
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def load_state() -> dict:
    if INGEST_STATE_PATH.exists():
        try:
            return json.loads(INGEST_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"events_last_offset": 0, "colls_seen_hashes": {}}


def save_state(state: dict) -> None:
    """Write indexer-state.json · no-op when content is unchanged.

    Day 11 (coll-0083 Tier-3): `ingest_events` called this after every
    poll even when 0 new events were appended · useless git noise.
    """
    new_text = json.dumps(state, ensure_ascii=False, indent=2)
    if INGEST_STATE_PATH.exists():
        try:
            if INGEST_STATE_PATH.read_text(encoding="utf-8-sig") == new_text:
                return
        except OSError:
            pass
    try:
        INGEST_STATE_PATH.write_text(new_text, encoding="utf-8")
    except OSError:
        pass


def sha1_of(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel_or_abs(p: Path, base: Path) -> str:
    """Render path relative to base when possible · absolute POSIX string otherwise.

    Day 13: guest-overlay coll files live outside central's WORKSPACE_ROOT ·
    plain `relative_to(WORKSPACE_ROOT)` would raise ValueError. Storing
    absolute paths for guest sources keeps the source_path field valid and
    traceable across scopes.
    """
    try:
        return str(p.relative_to(base)).replace("\\", "/")
    except ValueError:
        try:
            return str(p.resolve()).replace("\\", "/")
        except OSError:
            return str(p).replace("\\", "/")


# ─── ingest events.jsonl ──────────────────────────────────────────────

def ingest_events(conn: sqlite3.Connection, quiet: bool = False) -> int:
    if not EVENTS_PATH.exists():
        if not quiet:
            print(f"(no {EVENTS_PATH})")
        return 0
    state = load_state()
    offset = state.get("events_last_offset", 0)
    total_new = 0
    try:
        with open(EVENTS_PATH, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                conn.execute(
                    "INSERT INTO events (ts, type, session_id, tool, payload, source) "
                    "VALUES (?, ?, ?, ?, ?, 'events.jsonl')",
                    (
                        evt.get("ts", ""),
                        evt.get("type", "?"),
                        evt.get("session_id"),
                        evt.get("tool"),
                        json.dumps(evt.get("payload", {}), ensure_ascii=False),
                    ),
                )
                total_new += 1
            new_offset = f.tell()
        state["events_last_offset"] = new_offset
        save_state(state)
        conn.commit()
    except OSError:
        pass
    if not quiet:
        print(f"events ingested: +{total_new}")
    return total_new


# ─── parse coll markdown ──────────────────────────────────────────────

COLL_ID_RE = re.compile(r"coll-(\d+)")
DATE_RE = re.compile(r"\*\*Date\*\*:\s*([^\n·]+)", re.IGNORECASE)
TRIGGER_RE = re.compile(r"\*\*Trigger\*\*:\s*(.+?)(?=\n)", re.IGNORECASE)
FIELDS_LINE_RE = re.compile(r"\*\*Fields active\*\*:\s*(.+?)(?=\n)", re.IGNORECASE)
SPECIES_LINE_RE = re.compile(r"\*\*Active species\*\*:\s*(.+?)(?=\n)", re.IGNORECASE)
REACTION_RE = re.compile(r"\*\*Owner reaction\*\*:\s*(.+?)(?=\n)", re.IGNORECASE)
SEMANTIC_SECTION_RE = re.compile(r"##\s*本次语义\s*\n+\*\*(.+?)\*\*")
SEMANTIC_LINE_RE = re.compile(r"##\s*本次语义\s*\n+([^\n]+)")


FIELD_ASSIGN_RE = re.compile(r"([a-z][a-z0-9\-]{2,})\s*=\s*(-?\d+\.?\d*)")
SPECIES_ID_RE = re.compile(r"\b([a-z][a-z0-9\-]+-[a-z][a-z0-9\-]+)\b")

# Field id aliases · canonical form on the right.
# Older colls (0062 / 0064 / 0066 …) used short names like `ive` / `cold`
# which split stats in fields_usage. Without this map, the same field gets
# counted twice — once under the alias, once under the canonical name.
# Canonical list is the 9 starter fields + Pro fields that may appear.
FIELD_ALIASES: dict[str, str] = {
    "ive": "jony-ive",
    "cold": "cold-to-warm",
    "linus": "linus-torvalds",
    "rigor": "engineering-rigor",
    "deep": "deep-thinking",
    "brain": "brainstorm",
    "code-gen": "code-generator",
    "designer": "product-designer",
    "staff": "staff-engineer",
}


def canonical_field(name: str) -> str:
    """Map alias → canonical field id. Pass-through for unknown names so
    new fields (Pro / user-authored) keep working without registry update."""
    return FIELD_ALIASES.get(name.lower(), name.lower())


def parse_fields_line(line: str) -> dict[str, float]:
    """Extract name=value from a fields-active line · tolerant to
    parenthetical notes and unit suffixes · normalizes aliases.
    E.g. 'rigor=0.85, ive=0.40' → {'engineering-rigor': 0.85, 'jony-ive': 0.40}
    """
    out: dict[str, float] = {}
    if not line:
        return out
    for m in FIELD_ASSIGN_RE.finditer(line):
        name = canonical_field(m.group(1))
        try:
            out[name] = float(m.group(2))
        except ValueError:
            continue
    return out


def parse_species_line(line: str) -> list[str]:
    """Species IDs MUST contain at least one hyphen (two-part compound
    field names by convention · e.g. engineering-rigor-linus-torvalds).
    Reject bare numerics · hit-count noise · parenthetical annotations.
    """
    if not line:
        return []
    out: list[str] = []
    cleaned = re.sub(r"\([^)]*\)", " ", line)
    for m in SPECIES_ID_RE.finditer(cleaned):
        sid = m.group(1)
        if len(sid) >= 6 and sid not in out:
            out.append(sid)
    return out


def extract_semantic(content: str) -> str:
    m = SEMANTIC_SECTION_RE.search(content)
    if m:
        return m.group(1).strip()[:300]
    m = SEMANTIC_LINE_RE.search(content)
    if m:
        return m.group(1).strip()[:300]
    return ""


def ingest_colls(conn: sqlite3.Connection, quiet: bool = False) -> int:
    if not COLL_DIR.exists():
        return 0
    total_new = 0
    total_updated = 0
    for path in sorted(COLL_DIR.glob("coll-*.md")):
        if path.name.startswith("_"):
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        content_hash = sha1_of(raw)
        row = conn.execute(
            "SELECT content_hash FROM colls WHERE coll_id = ?",
            (path.stem,),
        ).fetchone()
        if row and row["content_hash"] == content_hash:
            continue

        m = COLL_ID_RE.search(path.stem)
        if not m:
            continue
        coll_id = path.stem

        date_m = DATE_RE.search(raw)
        created_at = date_m.group(1).strip()[:30] if date_m else path.stem

        trigger_m = TRIGGER_RE.search(raw)
        trigger = trigger_m.group(1).strip()[:500] if trigger_m else ""

        fields_m = FIELDS_LINE_RE.search(raw)
        fields = parse_fields_line(fields_m.group(1)) if fields_m else {}

        species_m = SPECIES_LINE_RE.search(raw)
        species = parse_species_line(species_m.group(1)) if species_m else []

        reaction_m = REACTION_RE.search(raw)
        reaction = reaction_m.group(1).strip()[:80] if reaction_m else ""

        semantic = extract_semantic(raw)

        if row:
            conn.execute(
                "UPDATE colls SET created_at=?, semantic=?, trigger_text=?, "
                "fields_json=?, species_json=?, owner_reaction=?, "
                "content_hash=?, indexed_at=? WHERE coll_id=?",
                (created_at, semantic, trigger, json.dumps(fields),
                 json.dumps(species), reaction, content_hash, now_iso(), coll_id),
            )
            total_updated += 1
        else:
            conn.execute(
                "INSERT INTO colls (coll_id, created_at, semantic, trigger_text, "
                "fields_json, species_json, owner_reaction, source_path, content_hash, indexed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (coll_id, created_at, semantic, trigger, json.dumps(fields),
                 json.dumps(species), reaction, _rel_or_abs(path, WORKSPACE_ROOT),
                 content_hash, now_iso()),
            )
            total_new += 1

        for field_name, concentration in fields.items():
            conn.execute(
                "INSERT INTO fields_usage (field_id, activation_count, last_activated_at, avg_concentration) "
                "VALUES (?, 1, ?, ?) "
                "ON CONFLICT(field_id) DO UPDATE SET "
                "activation_count = activation_count + 1, "
                "last_activated_at = excluded.last_activated_at, "
                "avg_concentration = (avg_concentration * activation_count + excluded.avg_concentration) "
                "                     / (activation_count + 1)",
                (field_name, created_at, concentration),
            )
            reaction_lower = (reaction or "").lower()
            if "positive" in reaction_lower or "好" in reaction_lower or "✓" in reaction_lower:
                conn.execute("UPDATE fields_usage SET positive_count = positive_count + 1 WHERE field_id = ?", (field_name,))
            elif "negative" in reaction_lower or "不好" in reaction_lower or "✗" in reaction_lower or "rejected" in reaction_lower:
                conn.execute("UPDATE fields_usage SET negative_count = negative_count + 1 WHERE field_id = ?", (field_name,))
            else:
                conn.execute("UPDATE fields_usage SET silent_count = silent_count + 1 WHERE field_id = ?", (field_name,))

        for sp in species:
            conn.execute(
                "INSERT INTO species_activations (species_id, fired_at, coll_ref, fields_snapshot, reaction) "
                "VALUES (?, ?, ?, ?, ?)",
                (sp, created_at, coll_id, json.dumps(fields), reaction),
            )

        if semantic:
            mem_id = f"mem-{coll_id}"
            mem_hash = sha1_of(semantic + trigger)
            importance = 0.6
            if species:
                importance = 0.7
            if any(s in trigger.lower() for s in ("绝不", "永不", "承诺", "决定", "禁止")):
                importance = 0.85
            conn.execute(
                "INSERT OR REPLACE INTO memories (id, created_at, updated_at, category, importance, content, "
                "summary, source_type, source_ref, tags, confidence) "
                "VALUES (?, ?, ?, 'experience', ?, ?, ?, 'coll', ?, ?, 1.0)",
                (mem_id, created_at, now_iso(), importance,
                 trigger + " → " + semantic, semantic,
                 coll_id, json.dumps(species)),
            )

    conn.commit()
    rebuild_fts(conn)
    if not quiet:
        print(f"colls ingested: +{total_new} new · {total_updated} updated")
    return total_new + total_updated


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Rebuild FTS5 index from memories table · standalone content · 
    simple model · no external-content sync needed."""
    conn.execute("DELETE FROM memories_fts")
    conn.execute(
        "INSERT INTO memories_fts (mem_id, category, content, summary, tags) "
        "SELECT id, category, content, COALESCE(summary,''), COALESCE(tags,'') FROM memories"
    )
    conn.commit()


# ─── ingest user-essence.md ──────────────────────────────────────────

ESSENCE_SECTION_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def ingest_essence(conn: sqlite3.Connection, quiet: bool = False) -> int:
    if not ESSENCE_PATH.exists():
        return 0
    try:
        raw = ESSENCE_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    content_hash = sha1_of(raw)
    essence_ref = _rel_or_abs(ESSENCE_PATH, WORKSPACE_ROOT)
    row = conn.execute("SELECT content_hash FROM files_meta WHERE path = ?",
                       (essence_ref,)).fetchone()
    if row and row["content_hash"] == content_hash:
        return 0

    sections = []
    positions = [m.start() for m in ESSENCE_SECTION_RE.finditer(raw)]
    positions.append(len(raw))
    for i in range(len(positions) - 1):
        chunk = raw[positions[i]:positions[i + 1]].strip()
        if not chunk:
            continue
        header_m = re.match(r"(#{1,3})\s+(.+)", chunk)
        if not header_m:
            continue
        level = len(header_m.group(1))
        title = header_m.group(2).strip()[:120]
        body = chunk[header_m.end():].strip()
        sections.append((level, title, body))

    new_count = 0
    for i, (level, title, body) in enumerate(sections):
        if not body:
            continue
        category = "identity"
        importance = 0.7
        tags: list[str] = []
        title_lower = title.lower()
        if any(k in title for k in ("偏好", "preference", "喜好")):
            category = "preference"
            importance = 0.8
            tags.append("preference")
        if any(k in title for k in ("厌恶", "dislike", "禁止")):
            category = "preference"
            importance = 0.9
            tags.append("aversion")
        if any(k in title for k in ("决策", "decision", "承诺", "pact")):
            category = "decision"
            importance = 0.95
            tags.append("decision")
        if any(k in title for k in ("规则", "rule")):
            category = "rule"
            importance = 0.85
        if any(k in title for k in ("身份", "identity")):
            category = "identity"
            importance = 0.9

        mem_id = f"mem-essence-{i:04d}"
        conn.execute(
            "INSERT OR REPLACE INTO memories (id, created_at, updated_at, category, importance, content, "
            "summary, source_type, source_ref, tags, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'essence', ?, ?, 1.0)",
            (mem_id, now_iso(), now_iso(), category, importance,
             f"[{title}]\n{body[:2000]}", title[:200],
             essence_ref, json.dumps(tags)),
        )
        new_count += 1

    conn.execute(
        "INSERT OR REPLACE INTO files_meta (path, mtime, content_hash, indexed_at) "
        "VALUES (?, ?, ?, ?)",
        (essence_ref,
         ESSENCE_PATH.stat().st_mtime, content_hash, now_iso()),
    )
    conn.commit()
    rebuild_fts(conn)
    if not quiet:
        print(f"essence sections ingested: {new_count}")
    return new_count


# ─── ingest species-registry.json ────────────────────────────────────

def ingest_species_registry(conn: sqlite3.Connection, quiet: bool = False) -> int:
    if not SPECIES_JSON.exists():
        return 0
    try:
        data = json.loads(SPECIES_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    species = data.get("species", {})
    n = 0
    for sid, s in species.items():
        conn.execute(
            "INSERT OR REPLACE INTO species_registry "
            "(species_id, niche, born_at, emerged_at, core_vector, health, "
            " activation_count, last_activated_at, origin, is_nursery) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (sid, s.get("niche"), s.get("born_at"), s.get("emerged_at"),
             json.dumps(s.get("core_vector", {})), s.get("health"),
             s.get("activation_count", 0), s.get("last_activated_at"),
             s.get("origin")),
        )
        n += 1

    if NURSERY_DIR.exists():
        for seed_path in NURSERY_DIR.glob("seed-*.seed.md"):
            # `Path.stem` strips only the last suffix (.md), leaving ".seed"
            # at the tail. Strip it explicitly so seed_id matches the canonical
            # form used elsewhere (e.g. `seed-engineering-rigor-jony-ive`).
            seed_id = seed_path.stem.removesuffix(".seed")
            try:
                raw = seed_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            ripe_m = re.search(r"ripening[^\n]*?(\d+)\s*/\s*(\d+)", raw, re.IGNORECASE)
            born_m = re.search(r"born[_\s]+at[:\s]*([^\n]+)", raw, re.IGNORECASE)
            conn.execute(
                "INSERT OR REPLACE INTO species_registry "
                "(species_id, niche, born_at, emerged_at, core_vector, health, "
                " activation_count, last_activated_at, origin, is_nursery) "
                "VALUES (?, 'nursery', ?, ?, ?, 'seed', ?, NULL, 'nursery', 1)",
                (seed_id,
                 born_m.group(1).strip()[:40] if born_m else None,
                 None,
                 json.dumps({}),
                 int(ripe_m.group(1)) if ripe_m else 0),
            )
            n += 1
    conn.commit()
    if not quiet:
        print(f"species entries ingested: {n}")
    return n


# ─── ingest fields definitions ───────────────────────────────────────

def ingest_fields_definitions(conn: sqlite3.Connection, quiet: bool = False) -> int:
    if not FIELDS_DIR.exists():
        return 0
    n = 0
    for field_path in FIELDS_DIR.rglob("*.field.md"):
        field_id = field_path.stem.replace(".field", "")
        existing = conn.execute(
            "SELECT field_id FROM fields_usage WHERE field_id = ?", (field_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO fields_usage (field_id, activation_count) VALUES (?, 0)",
                (field_id,),
            )
            n += 1
    conn.commit()
    if not quiet:
        print(f"fields definitions ensured: +{n}")
    return n


# ─── orchestration ───────────────────────────────────────────────────

def do_init() -> int:
    conn = connect()
    init_schema(conn)
    conn.close()
    print(f"schema initialized at {DB_PATH}")
    return 0


def consolidate_field_aliases(conn: sqlite3.Connection, quiet: bool = False) -> int:
    """Merge aliased rows in fields_usage into their canonical row.

    Runs every ingest · cheap (≤ N alias rows · usually 0 after first run).
    Logic per (alias, canonical) pair when both rows exist:
      · sum activation/positive/negative/silent counts
      · weighted-avg concentration (weighted by activation_count)
      · keep MAX(last_activated_at)
      · then DELETE the alias row
    If only the alias row exists · rename it to canonical.
    """
    merged = 0
    for alias, canonical in FIELD_ALIASES.items():
        if alias == canonical:
            continue
        a = conn.execute(
            "SELECT activation_count, last_activated_at, avg_concentration, "
            "       positive_count, negative_count, silent_count "
            "FROM fields_usage WHERE field_id = ?",
            (alias,),
        ).fetchone()
        if not a:
            continue
        c = conn.execute(
            "SELECT activation_count, last_activated_at, avg_concentration, "
            "       positive_count, negative_count, silent_count "
            "FROM fields_usage WHERE field_id = ?",
            (canonical,),
        ).fetchone()
        if c:
            ac = a["activation_count"] or 0
            cc = c["activation_count"] or 0
            total = ac + cc
            avg = (
                ((a["avg_concentration"] or 0.0) * ac + (c["avg_concentration"] or 0.0) * cc)
                / total
                if total
                else 0.0
            )
            last_a = a["last_activated_at"] or ""
            last_c = c["last_activated_at"] or ""
            last = max(last_a, last_c)
            conn.execute(
                "UPDATE fields_usage SET "
                "  activation_count = ?, "
                "  last_activated_at = ?, "
                "  avg_concentration = ?, "
                "  positive_count = ?, "
                "  negative_count = ?, "
                "  silent_count = ? "
                "WHERE field_id = ?",
                (
                    total,
                    last,
                    avg,
                    (a["positive_count"] or 0) + (c["positive_count"] or 0),
                    (a["negative_count"] or 0) + (c["negative_count"] or 0),
                    (a["silent_count"] or 0) + (c["silent_count"] or 0),
                    canonical,
                ),
            )
            conn.execute("DELETE FROM fields_usage WHERE field_id = ?", (alias,))
        else:
            conn.execute(
                "UPDATE fields_usage SET field_id = ? WHERE field_id = ?",
                (canonical, alias),
            )
        merged += 1
    if merged:
        conn.commit()
    if not quiet and merged:
        print(f"field aliases consolidated: {merged}")
    return merged


def do_ingest(quiet: bool = False) -> int:
    conn = connect()
    init_schema(conn)
    ingest_events(conn, quiet=quiet)
    ingest_colls(conn, quiet=quiet)
    ingest_essence(conn, quiet=quiet)
    ingest_species_registry(conn, quiet=quiet)
    ingest_fields_definitions(conn, quiet=quiet)
    consolidate_field_aliases(conn, quiet=quiet)
    rebuild_fts(conn)
    conn.close()
    return 0


def do_rebuild() -> int:
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except OSError:
            pass
    if INGEST_STATE_PATH.exists():
        try:
            INGEST_STATE_PATH.unlink()
        except OSError:
            pass
    print("rebuilding from scratch...")
    return do_ingest(quiet=False)


def do_stats() -> int:
    if not DB_PATH.exists():
        print("(no index.db · run `init` then `ingest` first)")
        return 1
    conn = connect()
    tables = [
        ("events", "SELECT COUNT(*) FROM events"),
        ("colls", "SELECT COUNT(*) FROM colls"),
        ("memories", "SELECT COUNT(*) FROM memories"),
        ("species_registry", "SELECT COUNT(*) FROM species_registry"),
        ("species_activations", "SELECT COUNT(*) FROM species_activations"),
        ("fields_usage", "SELECT COUNT(*) FROM fields_usage"),
        ("digests", "SELECT COUNT(*) FROM digests"),
    ]
    print(f"DB: {DB_PATH} · {DB_PATH.stat().st_size} bytes")
    print()
    for name, q in tables:
        try:
            row = conn.execute(q).fetchone()
            print(f"  {name:25s} {row[0]:6d}")
        except sqlite3.OperationalError as e:
            print(f"  {name:25s} (error: {e})")

    print()
    print("top 5 memories by importance:")
    rows = conn.execute(
        "SELECT id, category, importance, substr(content, 1, 80) AS c FROM memories "
        "ORDER BY importance DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(f"  {r['id']} [{r['category']:10s}] imp={r['importance']:.2f} · {r['c']}")

    print()
    print("top 5 fields by usage:")
    rows = conn.execute(
        "SELECT field_id, activation_count, avg_concentration, "
        "positive_count, negative_count, silent_count "
        "FROM fields_usage WHERE activation_count > 0 ORDER BY activation_count DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(f"  {r['field_id']:25s} n={r['activation_count']:3d} avg={r['avg_concentration'] or 0:.2f} "
              f"+{r['positive_count']} -{r['negative_count']} ?{r['silent_count']}")

    print()
    print("species activations timeline (recent 5):")
    rows = conn.execute(
        "SELECT species_id, fired_at, coll_ref FROM species_activations "
        "ORDER BY fired_at DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(f"  {r['fired_at'][:16]:20s} {r['species_id']:40s} ← {r['coll_ref']}")

    conn.close()
    return 0


def _activate_overlay(args) -> None:
    """Reassign module-global paths based on `--path` / cwd-walk.

    Day 13 · PATH-RESOLUTION-SPEC §3.1: DATA_DIR / DB_PATH / EVENTS_PATH /
    INGEST_STATE_PATH / COLL_DIR now follow the active overlay. Layer A
    sources that are cross-scope (essence / species / fields) stay pinned
    to central (see §5).
    """
    global DATA_DIR, DB_PATH, EVENTS_PATH, INGEST_STATE_PATH, COLL_DIR
    overlay, source = activate_overlay_for_cli(args, announce=not args.quiet)
    DATA_DIR = overlay
    DB_PATH = overlay / "index.db"
    EVENTS_PATH = overlay / "events.jsonl"
    INGEST_STATE_PATH = overlay / "indexer-state.json"
    # Prefer overlay/coll/ when it exists (guest projects) · fall back to
    # central's gen6-noesis/collapse-events (central scope).
    overlay_coll = overlay / "coll"
    if source != "central" and overlay_coll.exists():
        COLL_DIR = overlay_coll
    else:
        COLL_DIR = CENTRAL_COLL_DIR


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether Layer A → Layer B indexer")
    ap.add_argument("cmd", choices=["init", "ingest", "rebuild", "stats"])
    ap.add_argument("--quiet", action="store_true")
    add_path_arg(ap)
    args = ap.parse_args()

    _activate_overlay(args)

    if args.cmd == "init":
        return do_init()
    if args.cmd == "ingest":
        return do_ingest(quiet=args.quiet)
    if args.cmd == "rebuild":
        return do_rebuild()
    if args.cmd == "stats":
        return do_stats()
    return 0


if __name__ == "__main__":
    sys.exit(main())
