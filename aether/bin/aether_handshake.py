#!/usr/bin/env python3
"""
aether_handshake.py — PROTOCOL 0 auto-handshake · cross-session memory injection

Cursor's sessionStart hook calls this CLI. It reads the 6 core files (pact +
essence + plan + last 3 coll + latest handover + rules), compresses them into
a briefing, and emits it as Cursor-hook-contract JSON on stdout.

Output shape (sessionStart event):
    {
      "additional_context": "<markdown briefing · injected at session start>"
    }

This means Owner doesn't need to type "aether handshake" · opening a new chat
auto-syncs memory. AI's first sight = full cross-session context.

CLI usage:
    python bin/aether_handshake.py                    # print briefing (debug)
    python bin/aether_handshake.py --json             # emit Cursor hook JSON
    python bin/aether_handshake.py --max-chars 6000   # control injected size
    python bin/aether_handshake.py --test             # dry-run · show structure
    python bin/aether_handshake.py --scope guest      # force guest mode (debug)
    python bin/aether_handshake.py --workspace <path> # simulate a workspace

Design principles:
- Zero dependency (Python stdlib)
- Fail-open (returns empty additional_context on error · never blocks session)
- Size budget (briefing too large eats tokens · default 4000 / 1400 chars)

──────────────────────────────────────────────────────────────────────
Day 9 (coll-0081) · scope awareness

Owner installed Aether globally on Day 8 (~/.cursor/hooks.json · central is
the skills workspace). Until Day 9, this script ignored which project Cursor
had actually opened — it always read central's handover / coll / index.db,
so EVERY project got the same "Day 9/30 · handover: day-8-handover.md" line.
Owner's Day 9 first-chat complaint: "每个项目都会有这一句话 · 为什么没有
对应的区分啊" exposed the read-write asymmetry (writes honored
payload.workspace_roots, reads didn't).

Day 9 fix (stop-the-bleed · NOT full federation):
  1. resolve_workspace_root(payload)  — detect current project root
  2. detect_scope(ws_root)             — 'dev-self' if = central · else 'guest'
  3. build_briefing(payload) dispatches:
       · dev-self → full briefing (unchanged Day 1-8 behavior)
       · guest    → lean briefing · pact + 5-mode + scope marker · no
                    Aether-dev handover / coll (those belong to central)

Day 10 P0 (federated memory · coll-0082) · DONE:
  · ~/.aether-core/ holds identity/pact/fields/species (aether_federate.py)
  · <project>/.aether/ holds per-project handover/coll/tasks (aether_project.py)
  · _build_guest_briefing renders 4 blocks from the project overlay when
    present (overlay manifest · latest handover · last 3 coll · open P0)
  · pact falls back to central labs/chronicle when core not initialized

Day 11 (coll-0083) · D-layer read/write asymmetry fix:
  · Day 9 fixed B-layer (this script now reads per-project).
  · Day 10 shipped the infrastructure (core + overlay + two new CLIs).
  · Day 11 closes the loop: aether_tasks/daily/doctor now resolve the
    active overlay via aether_paths.resolve_active_overlay(). Handshake
    itself is unchanged · the fix was on the CLI side.

Day 12 (coll-0092) · status line scope dispatch:
  · dev-self                       → central data (unchanged)
  · guest + overlay + handover     → overlay's latest day-*-handover.md
  · guest + overlay + no handover  → Day 1/30 · ?/? · handover: day-0-handover.md
  · guest + no overlay             → unregistered · handover: none

Status line matches one of two new RULE 00 regexes (see aether.mdc):
    ^⟁ Aether · Day \\d+/30 · .+? · scope: [^·]+ · handover: day-\\d+-handover\\.md$
    ^⟁ Aether · unregistered · scope: guest @ [^·]+ · handover: none$

(`.+?` = non-greedy · absorbs score segments with interior `·` like
 `86/100 (32 ok · 2 warn · 3 fail)` while stopping at the `· scope:` anchor.)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent              # aether/
WORKSPACE_ROOT = ROOT.parent                                # git repo root (central · skills)

DEFAULT_MAX_CHARS = 4000
# Guest budget · lean when no overlay, but needs room when overlay is populated
# (local handover excerpt + 3 colls + open P0). 3000 = 25% less than dev-self.
DEFAULT_GUEST_MAX_CHARS = 3000


# ─── scope detection · coll-0081 (Day 9) ─────────────────────────────

def resolve_workspace_root(payload: dict | None = None) -> Path:
    """Resolve the user's CURRENT workspace root · not central aether.

    Order:
      1. payload.workspace_roots[0]  (Cursor hook · most authoritative)
      2. AETHER_WORKSPACE env var    (testing / CLI override)
      3. os.getcwd()                 (CLI fallback · when Owner runs a tool)
      4. WORKSPACE_ROOT              (ultimate fallback · central skills)

    Windows quirk: Cursor sends '/c:/Users/...' style · normalize to 'c:/...'.
    Same logic as aether_events.resolve_data_dir() uses.
    """
    if isinstance(payload, dict):
        roots = payload.get("workspace_roots") or []
        if isinstance(roots, list) and roots:
            try:
                first = str(roots[0]).strip()
                if len(first) >= 4 and first[0] == "/" and first[2] == ":":
                    first = first[1] + ":" + first[3:]
                p = Path(first).expanduser()
                if p.exists() and p.is_dir():
                    return p.resolve()
            except Exception:
                pass
    env = os.environ.get("AETHER_WORKSPACE", "").strip()
    if env:
        try:
            p = Path(env).expanduser()
            if p.exists() and p.is_dir():
                return p.resolve()
        except Exception:
            pass
    try:
        cwd = Path(os.getcwd()).resolve()
        if cwd.exists():
            return cwd
    except Exception:
        pass
    return WORKSPACE_ROOT.resolve()


def detect_scope(ws_root: Path, override: str | None = None) -> str:
    """Return 'dev-self' if ws_root is central skills workspace · else 'guest'.

    override: CLI flag ('dev-self' | 'guest' | None) · beats detection.
    """
    if override in ("dev-self", "guest"):
        return override
    try:
        return "dev-self" if ws_root.resolve() == WORKSPACE_ROOT.resolve() else "guest"
    except Exception:
        return "guest"


def _short_project_name(ws_root: Path) -> str:
    """Short display name · last path segment · clipped for status line."""
    try:
        name = ws_root.name or str(ws_root)
        if len(name) > 32:
            name = name[:29] + "..."
        return name
    except Exception:
        return "unknown"


# ─── A-layer readers · central-only (all paths rooted at central ROOT) ─

def read_safe(path: Path, max_chars: int | None = None) -> str:
    try:
        txt = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    if max_chars and len(txt) > max_chars:
        return txt[:max_chars] + "\n...[truncated]..."
    return txt


def latest_handover() -> Path | None:
    """Central's latest handover · Day N/30 tracking belongs to central only.

    Day 10 federation will add latest_local_handover(ws_root) to let guest
    projects have their own day counters.

    Day 10 session 5 · coll-0089 · **数字序 bug 修复**:
    Before: `sorted(glob("day-*-handover.md"))[-1]` 用字典序 ·
            day-10 < day-2(因 '1' < '2')· 所以 day-9 永远被认为是 max ·
            status line 卡死在 Day 10。
    After:  按 `day-N` 中 N 的数字值排序 · day-10 真的 > day-9。
    """
    daily = ROOT / "docs" / "daily"
    if not daily.exists():
        return None
    files = list(daily.glob("day-*-handover.md"))
    if not files:
        return None

    def day_num(p: Path) -> int:
        m = re.match(r"day-(\d+)-handover\.md", p.name)
        return int(m.group(1)) if m else -1

    return max(files, key=day_num)


def latest_colls(n: int = 3) -> list[Path]:
    coll_dir = ROOT / "gen6-noesis" / "collapse-events"
    if not coll_dir.exists():
        return []
    files = sorted(coll_dir.glob("coll-*.md"), reverse=True)
    return files[:n]


def b_layer_briefing(timeout: float = 3.0) -> str | None:
    """Render the briefing from Layer B (central's SQLite index).

    A-layer fallback kicks in only when index.db is missing/slow/erroring.
    Central-scope only — guest projects' local index.db (if any · Day 10+)
    will be queried via a separate path.
    """
    db_path = WORKSPACE_ROOT / ".aether" / "index.db"
    if not db_path.exists():
        return None
    try:
        import subprocess
        r = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "aether_query.py"), "--briefing"],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8",
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        return r.stdout.strip()
    except Exception:
        return None


def extract_semantic(coll_path: Path) -> str:
    """Pull the single-line semantic summary from a coll (template-dependent)."""
    txt = read_safe(coll_path, max_chars=4000)
    m = re.search(r"##\s*本次语义\s*\n+\*\*(.+?)\*\*", txt)
    if m:
        return m.group(1).strip()
    m = re.search(r"##\s*本次语义\s*\n+([^\n]+)", txt)
    if m:
        return m.group(1).strip()[:200]
    m = re.search(r"collapse_class:\s*([^\n]+)", txt)
    if m:
        return m.group(1).strip()
    return "(no semantic summary found)"


def current_day() -> str:
    """Derive current day number from central handover names · fallback chain.

    Signal 1 (primary): latest handover file name (day-N-handover.md written
        end of Day N → today = Day N+1). Updates every session end.
    Signal 2 (backup): 30-day-plan.md progress bar.
    Signal 3 (fallback): pact date arithmetic (2026-04-17 = Day 1).

    Day N/30 is OWNER-scoped (not project-scoped) · same value across guest
    projects · Owner's 30-day commitment doesn't pause when they switch repos.
    """
    ho = latest_handover()
    if ho:
        m = re.match(r"day-(\d+)-handover\.md", ho.name)
        if m:
            return str(int(m.group(1)) + 1)
    plan = ROOT / "docs" / "30-day-plan.md"
    if plan.exists():
        txt = read_safe(plan, max_chars=3000)
        m = re.search(r"\[[\u2588\u2592\u2591 ]+\]\s*(\d+)\s*/\s*30", txt)
        if m:
            return m.group(1)
        m = re.search(r"(\d+)/30 days", txt)
        if m:
            return m.group(1)
    try:
        from datetime import date
        start = date(2026, 4, 17)
        delta = (date.today() - start).days + 1
        return str(max(1, delta))
    except Exception:
        return "?"


def selfcheck_score() -> str:
    """Call aether_selfcheck.py --json · return compact score string."""
    try:
        import subprocess
        r = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "aether_selfcheck.py"), "--json"],
            capture_output=True, text=True, timeout=15, encoding="utf-8",
        )
        if r.returncode not in (0, 1, 2):
            return "?/100"
        checks = json.loads(r.stdout)
        if not isinstance(checks, list) or not checks:
            return "?/100"
        total = len(checks)
        ok = sum(1 for c in checks if c.get("status") == "ok")
        warn = sum(1 for c in checks if c.get("status") == "warn")
        fail = sum(1 for c in checks if c.get("status") == "fail")
        score = int(ok / total * 100)
        return f"{score}/100 ({ok} ok · {warn} warn · {fail} fail)"
    except Exception:
        return "?/100 (selfcheck unavailable)"


# ─── scope-aware readers (Day 12 · coll-0092) ────────────────────────
#
# Before Day 12, `_status_line` fed `current_day()` / `selfcheck_score()` /
# `latest_handover()` to BOTH dev-self and guest briefings · so a guest
# project's status line showed central's "Day 12/30 · 100/100 · handover:
# day-11-handover.md" · causing cross-project concept pollution.
#
# Day 9-11 fixed the hook + CLI layers' read/write asymmetry but left
# status line reads centralized. Day 12 closes the loop by introducing
# scope-aware readers that dispatch on (scope, overlay_dir):
#
#   dev-self                       → central data (unchanged)
#   guest + overlay + handover     → overlay's latest day-*-handover.md
#   guest + overlay + no handover  → "1" (freshly inited · Day 1 semantic)
#   guest + no overlay             → None (signals unregistered)
#
# Keeping `current_day()` / `selfcheck_score()` / `latest_handover()` as
# the central-only primitives · these new functions are scope dispatchers.

def _latest_local_handover(overlay_dir: Path) -> Path | None:
    """Overlay-local max-day handover · number sort (not lexicographic)."""
    ho_dir = overlay_dir / "handover"
    if not ho_dir.exists():
        return None
    files = list(ho_dir.glob("day-*-handover.md"))
    if not files:
        return None

    def day_num(p: Path) -> int:
        m = re.match(r"day-(\d+)-handover\.md", p.name)
        return int(m.group(1)) if m else -1

    return max(files, key=day_num)


def current_day_for_scope(scope: str, overlay_dir: Path | None) -> str | None:
    """Day N string · or None when unregistered.

    Returns None signals the caller (status line) to render the
    "unregistered" alternative form. Day 0 is reserved for "just inited
    but no handover yet" · displayed as "Day 1" (human-friendly).
    """
    if scope == "dev-self":
        return current_day()
    if overlay_dir is None or not overlay_dir.exists():
        return None
    ho = _latest_local_handover(overlay_dir)
    if ho is None:
        return "1"
    m = re.match(r"day-(\d+)-handover\.md", ho.name)
    return str(int(m.group(1)) + 1) if m else "1"


def selfcheck_score_for_scope(scope: str, overlay_dir: Path | None) -> str:
    """Central selfcheck only makes sense for dev-self.

    Day 13 follow-up: `aether_selfcheck.py --overlay <path>` will score
    overlay health (L9 tasks · L11 day drift · etc.). Until then, guest
    renders '?/?' to stay honest — refusing to paste central's 86/100 on
    an unrelated project.
    """
    if scope == "dev-self":
        return selfcheck_score()
    return "?/?"


def handover_name_for_scope(scope: str, overlay_dir: Path | None) -> str:
    """'none' when no overlay · 'day-0-handover.md' when overlay + empty ·
    overlay's latest otherwise."""
    if scope == "dev-self":
        ho = latest_handover()
        return ho.name if ho else "day-0-handover.md"
    if overlay_dir is None or not overlay_dir.exists():
        return "none"
    ho = _latest_local_handover(overlay_dir)
    return ho.name if ho else "day-0-handover.md"


# ─── status line · regex-compatible ──────────────────────────────────

def _status_line(day: str | None, score: str, scope: str, scope_detail: str,
                 handover_name: str) -> str:
    """Build the mandatory RULE 00 status line.

    Two alternative forms · both MUST match one of the aether.mdc regexes:
      registered:    ^⟁ Aether · Day \\d+/30 · .+? · scope: [^·]+ · handover: day-\\d+-handover\\.md$
      unregistered:  ^⟁ Aether · unregistered · scope: guest @ [^·]+ · handover: none$

    `day=None` + `handover_name="none"` signals the unregistered form.
    This only happens in `scope=guest` when the project has no `.aether/`
    overlay · Owner has not run `aether project init`.
    """
    if scope == "dev-self":
        tag = "scope: dev-self"
    else:
        tag = f"scope: guest @ {scope_detail}"

    if day is None:  # unregistered · guest without overlay
        return f"⟁ Aether · unregistered · {tag} · handover: none"
    return f"⟁ Aether · Day {day}/30 · {score} · {tag} · handover: {handover_name}"


# ─── full briefing · dev-self mode (central skills · Day 1-8 behavior) ─

def _build_dev_self_briefing(max_chars: int) -> str:
    day = current_day()
    score = selfcheck_score()
    ho = latest_handover()
    handover_name = ho.name if ho else "day-0-handover.md"
    status_line = _status_line(day, score, "dev-self", "", handover_name)

    lines: list[str] = []
    lines.append("# ⟁ Aether Session · Auto-Handshake")
    lines.append("")
    lines.append(
        "> **RULE 0 · MANDATORY**: the first line of your first response in this "
        "session MUST be the exact status line below (inside a code block). "
        "This is how Owner verifies the handshake hook fired. No deviation. "
        "Applies to EVERY model tier · even 'quick' / 'brief' responses."
    )
    lines.append("")
    lines.append("```")
    lines.append(status_line)
    lines.append("```")
    lines.append("")
    lines.append(
        f"_Injected at {datetime.now(timezone.utc).isoformat()} by "
        f"aether_handshake.py · scope=dev-self_"
    )
    lines.append("")
    lines.append("You are resuming work in the **Aether private workspace** (central skills · dev-self).")
    lines.append(
        "PROTOCOL 0 is satisfied by this auto-injection — you do NOT need to "
        "re-read the 6 context files unless the user explicitly types `handshake` or you detect a gap."
    )
    lines.append("")

    pact = ROOT / "labs" / "chronicle" / "collaboration-pact-2026-04-17.md"
    if pact.exists():
        txt = read_safe(pact, max_chars=800)
        lines.append("## Contract (excerpt)")
        lines.append("")
        m = re.search(r"##[^\n]*(?:承诺|核心|第三节)[^\n]*\n(.+?)(?=\n##|\Z)", txt, re.DOTALL)
        core = m.group(1).strip()[:500] if m else txt[:500]
        lines.append(core)
        lines.append("")

    lines.append(f"## Day {day} / 30 · 30-day plan")
    lines.append("")

    if ho:
        lines.append(
            f"### Latest handover · `{ho.name}`"
            "(**read this first** — it has today's P0/P1/P2 list)"
        )
        lines.append("")
        ho_txt = read_safe(ho, max_chars=1200)
        lines.append("```markdown")
        lines.append(ho_txt.strip())
        lines.append("```")
        lines.append("")

    b_block = b_layer_briefing()
    if b_block:
        lines.append("## Memory snapshot (Layer B · index.db)")
        lines.append("")
        lines.append(b_block)
        lines.append("")
    else:
        colls = latest_colls(3)
        if colls:
            lines.append("## Recent collapses (semantic summary · A-layer fallback)")
            lines.append("")
            for p in colls:
                cid = p.stem
                sem = extract_semantic(p)
                lines.append(f"- **{cid}** · {sem}")
            lines.append("")

    lines.append("## Current state")
    lines.append("")
    lines.append(f"- Health: **{score}**")
    stats = ROOT / "site" / "public" / "stats.json"
    if stats.exists():
        try:
            d = json.loads(read_safe(stats))
            a = d.get("aether", {})
            lines.append(
                f"- Collapses: {a.get('collapses', '?')} · Fields: {a.get('fields', '?')} · "
                f"CLI: {a.get('cli_tools', '?')}"
            )
        except Exception:
            pass
    lines.append("")

    lines.append("## Your job in this session")
    lines.append("")
    lines.append(
        "Behavior rules (the status line is already mandated by RULE 0 at the top):"
    )
    lines.append("")
    lines.append(
        "1. If user types 'start' / '开始' / '继续' / natural instruction · "
        "execute per the handover P0 list above (no meta-discussion about "
        "'what should we do')."
    )
    lines.append(
        "2. If user types 'handshake' / '同步一下' · short confirmation only · "
        "context is already loaded · the status line IS the confirmation."
    )
    lines.append(
        "3. If user asks unrelated questions · answer normally · status line still goes first."
    )
    lines.append(
        "4. If user asks specific questions answerable from this briefing "
        "(`今天 Day 几` / `selfcheck 多少分` / `最近 coll 讲了啥`) · "
        "answer concretely · don't say 'I don't know'."
    )
    lines.append("")
    lines.append("_Full PROTOCOL 0 details: `.cursor/rules/aether.mdc`_")

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n...[briefing truncated to fit token budget]..."
    return result


# ─── lean briefing · guest mode (any non-central workspace) ─────────

def _build_guest_briefing(ws_root: Path, max_chars: int) -> str:
    """Lean briefing for GUEST projects (any workspace ≠ central skills).

    Design principle (coll-0081 · Day 9): guest projects get Owner's
    IDENTITY and USAGE RULES only · NOT Aether-dev-specific coll / handover
    / tasks. Day N/30 stays because Owner's 30-day commitment doesn't pause
    when switching repos. But handover content / recent coll / species
    registry belong to central's dev narrative — pure noise for novel-project
    or OpenClaw sessions.

    Overlay (future · Day 10 P0 federation): if ws_root/.aether/handover/
    or ws_root/.aether/coll/ exists, surface THOSE instead of central's.
    Today we detect presence and invite `aether project init` (Day 10).

    Day 12 (coll-0092): status line now reads overlay · not central.
    Previously guest always saw central's Day 12/100/day-11-handover · now
    guest with overlay sees its own day/score/handover · guest without
    overlay sees "unregistered" · no more concept pollution.
    """
    overlay_dir = ws_root / ".aether"
    day = current_day_for_scope("guest", overlay_dir)
    score = selfcheck_score_for_scope("guest", overlay_dir)
    handover_name = handover_name_for_scope("guest", overlay_dir)
    proj_name = _short_project_name(ws_root)
    status_line = _status_line(day, score, "guest", proj_name, handover_name)

    lines: list[str] = []
    lines.append("# ⟁ Aether Session · Guest Mode")
    lines.append("")
    lines.append(
        "> **RULE 0 · MANDATORY**: the first line of your first response in this "
        "session MUST be the exact status line below (inside a code block). "
        "No deviation. This is how Owner verifies Aether is running."
    )
    lines.append("")
    lines.append("```")
    lines.append(status_line)
    lines.append("```")
    lines.append("")
    lines.append(
        f"_Injected at {datetime.now(timezone.utc).isoformat()} by aether_handshake.py_  \n"
        f"_scope=guest · workspace={ws_root}_  \n"
        f"_central Aether = {WORKSPACE_ROOT}_"
    )
    lines.append("")
    lines.append(
        "You are running Aether in **GUEST MODE** inside a non-central project. "
        "Aether-dev state (handovers / coll / tasks / species / 30-day plan "
        "content) lives in the central skills workspace and is intentionally "
        "NOT shown here — it would be noise for whatever work is happening "
        "in this project."
    )
    lines.append("")
    lines.append("**What IS active in guest mode**:")
    lines.append("")
    lines.append(
        "- **5-mode auto-activation** (triggers listed in "
        "`~/.cursor/rules/aether.mdc`): `CODE-REVIEW` · `CODE-WRITE` · "
        "`THINK` · `WRITE` · `BRAINSTORM` — match user phrasing → silently "
        "prepend `[mode: ... · fields: ...]` to reply."
    )
    lines.append(
        "- **Per-project data isolation**: events / transcripts / "
        f"agent-responses are written to `{ws_root}/.aether/` "
        "(already configured · coll-0072 transcript_path pipeline)."
    )
    lines.append(
        "- **Status line** (RULE 00) · above · quote verbatim on first reply of this session."
    )
    lines.append("")

    # Identity · Day 10 prefers ~/.aether-core/core/pact.md · fallback to
    # central labs/chronicle (when Owner hasn't run aether federate init-core).
    core_pact = Path.home() / ".aether-core" / "core" / "pact.md"
    central_pact = ROOT / "labs" / "chronicle" / "collaboration-pact-2026-04-17.md"
    pact = core_pact if core_pact.exists() else central_pact
    pact_source = "core" if core_pact.exists() else "central-fallback"
    if pact.exists():
        txt = read_safe(pact, max_chars=600)
        m = re.search(r"##[^\n]*(?:承诺|核心|第三节)[^\n]*\n(.+?)(?=\n##|\Z)", txt, re.DOTALL)
        if m:
            core = m.group(1).strip()[:400]
            lines.append(f"## Owner · persistent identity ({pact_source} pact)")
            lines.append("")
            lines.append(core)
            lines.append("")

    # Project overlay · Day 10 P0 renders the actual contents (Day 9 just
    # listed counts). Reads 3 things if present:
    #   · latest local handover (last day-*-handover.md) · excerpted
    #   · last 3 local colls (coll-*.md) · semantic summary one-liner
    #   · open P0 tasks from tasks.jsonl · trimmed list
    overlay_dir = ws_root / ".aether"
    local_handover_dir = overlay_dir / "handover"
    local_coll_dir = overlay_dir / "coll"
    local_tasks = overlay_dir / "tasks.jsonl"
    manifest_path = overlay_dir / "manifest.json"
    has_overlay = (local_handover_dir.exists() or local_coll_dir.exists()
                   or manifest_path.exists() or local_tasks.exists())

    lines.append(f"## Project overlay @ `{proj_name}`")
    lines.append("")
    if has_overlay:
        # Overlay version info (when manifest present)
        if manifest_path.exists():
            try:
                mf = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                ov_ver = mf.get("overlay_version", "?")
                init_at = (mf.get("init_at") or "?")[:19]
                lines.append(
                    f"_overlay v{ov_ver} · initialized {init_at} · "
                    f"linked_core_version={mf.get('linked_core_version', '?')}_"
                )
                lines.append("")
            except Exception:
                pass

        # Latest local handover (inline · ~500 chars cap to stay within budget)
        # Day 10 session 5 · 同 latest_handover() 的字典序 bug 修复 · 按 day-N 的 N 数值排
        if local_handover_dir.exists():
            hos = list(local_handover_dir.glob("day-*-handover.md"))
            if hos:
                def _day_num_local(p):
                    m = re.match(r"day-(\d+)-handover\.md", p.name)
                    return int(m.group(1)) if m else -1
                latest_local_ho = max(hos, key=_day_num_local)
                # Re-sort for "older handover count" display below
                hos = sorted(hos, key=_day_num_local)
                lines.append(f"### Local handover · `{latest_local_ho.name}`")
                lines.append("")
                ho_txt = read_safe(latest_local_ho, max_chars=500)
                lines.append("```markdown")
                lines.append(ho_txt.strip())
                lines.append("```")
                lines.append("")
                if len(hos) > 1:
                    lines.append(f"_(+{len(hos) - 1} older local handover(s) in `{local_handover_dir.name}/`)_")
                    lines.append("")

        # Last 3 local colls (semantic summary only · compact)
        if local_coll_dir.exists():
            local_colls = sorted(local_coll_dir.glob("coll-*.md"), reverse=True)[:3]
            if local_colls:
                lines.append("### Recent local collapses")
                lines.append("")
                for p in local_colls:
                    cid = p.stem
                    sem = extract_semantic(p)[:160]
                    lines.append(f"- **{cid}** · {sem}")
                lines.append("")

        # Open P0 tasks (overlay-local tasks.jsonl)
        if local_tasks.exists():
            try:
                p0s = []
                with open(local_tasks, "r", encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        ln = ln.strip()
                        if not ln:
                            continue
                        try:
                            t = json.loads(ln)
                        except json.JSONDecodeError:
                            continue
                        if t.get("status") == "open" and t.get("priority") == "P0":
                            p0s.append(t)
                if p0s:
                    lines.append(f"### Open P0 tasks · {len(p0s)} item(s)")
                    lines.append("")
                    for t in p0s[:5]:
                        tid = t.get("id", "?")
                        title = (t.get("title") or "")[:80]
                        lines.append(f"- **{tid}** · {title}")
                    if len(p0s) > 5:
                        lines.append(f"- _...(+{len(p0s) - 5} more)_")
                    lines.append("")
            except OSError:
                pass
    else:
        lines.append(
            "No project-local Aether overlay yet. Nothing cross-contaminates "
            "from the central Aether-dev workspace. Work normally."
        )
        lines.append("")
        lines.append(
            "_To give THIS project its own handover / coll / tasks ledger · "
            "run `aether project init --apply` in the project root._"
        )
    lines.append("")

    lines.append("## Your job in this session")
    lines.append("")
    lines.append(
        "1. Quote the status line above · verbatim · as first line of first reply (RULE 00)."
    )
    lines.append(
        "2. Apply 5-mode auto-activation when user phrasing triggers "
        "(see `~/.cursor/rules/aether.mdc`)."
    )
    lines.append(
        "3. Work on the project at hand. Do NOT inject Aether-dev "
        "handovers / coll / 30-day-plan content unless user asks · they "
        "belong to the central skills workspace, not here."
    )
    lines.append(
        "4. If user types `handshake` / `同步一下` · short confirmation · "
        "status line IS the confirmation."
    )
    lines.append("")
    lines.append(
        f"_Central Aether-dev state: Day {day}/30 · {score} · "
        f"handover {handover_name} (FYI only · not your topic here)_"
    )

    result = "\n".join(lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n...[briefing truncated to fit token budget]..."
    return result


# ─── dispatch ─────────────────────────────────────────────────────────

def build_briefing(payload: dict | None = None,
                   max_chars: int | None = None,
                   scope_override: str | None = None) -> str:
    """Dispatch the briefing build based on scope (dev-self vs guest).

    Args:
      payload:        Cursor hook payload (carries workspace_roots).
                      None → fall back to cwd / env.
      max_chars:      optional override. Defaults:
                      · dev-self: DEFAULT_MAX_CHARS (4000)
                      · guest:    DEFAULT_GUEST_MAX_CHARS (1400 · ~1/3)
      scope_override: force 'dev-self' | 'guest' (for --scope CLI flag).

    Back-compat: older callers passed an int max_chars positionally. We
    detect that case (first arg not dict/None) and treat it as max_chars.
    """
    if payload is not None and not isinstance(payload, dict):
        try:
            max_chars = int(payload)
            payload = None
        except (TypeError, ValueError):
            payload = None

    ws_root = resolve_workspace_root(payload)
    scope = detect_scope(ws_root, override=scope_override)

    if scope == "dev-self":
        return _build_dev_self_briefing(max_chars or DEFAULT_MAX_CHARS)
    return _build_guest_briefing(ws_root, max_chars or DEFAULT_GUEST_MAX_CHARS)


# ─── CLI ──────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Aether PROTOCOL 0 auto-handshake")
    ap.add_argument("--json", action="store_true",
                    help="output Cursor-hook JSON (additional_context) to stdout")
    ap.add_argument("--max-chars", type=int, default=None,
                    help="override max chars (default 4000 dev-self · 1400 guest)")
    ap.add_argument("--scope", choices=("dev-self", "guest", "auto"),
                    default="auto",
                    help="force scope · default 'auto' infers from cwd / env")
    ap.add_argument("--workspace",
                    help="simulate a workspace root (overrides cwd · debug/test)")
    ap.add_argument("--test", action="store_true",
                    help="dry-run · print briefing length + status line + first 300 chars")
    args = ap.parse_args()

    if args.workspace:
        os.environ["AETHER_WORKSPACE"] = args.workspace

    scope_override = None if args.scope == "auto" else args.scope

    briefing = build_briefing(
        payload=None,
        max_chars=args.max_chars,
        scope_override=scope_override,
    )

    if args.test:
        print(f"Briefing length: {len(briefing)} chars")
        m = re.search(r"```\n(.+?)\n```", briefing)
        if m:
            print(f"Status line: {m.group(1)}")
        print("--- first 300 ---")
        print(briefing[:300])
        return 0

    if args.json:
        print(json.dumps({"additional_context": briefing}, ensure_ascii=False))
        return 0

    print(briefing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
