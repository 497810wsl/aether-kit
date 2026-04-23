#!/usr/bin/env python3
"""
aether_selfcheck.py — Aether 端到端架构健康检查

Scans all 8 layers of the Aether architecture and reports:
  - What's connected and working
  - What's declared but broken
  - What's missing entirely
  - Recommended fix order

Usage:
    python bin/aether_selfcheck.py              # full diagnostic
    python bin/aether_selfcheck.py --fix        # auto-fix safe issues
    python bin/aether_selfcheck.py --json       # machine output

Exit code: 0 if all green, 1 if any red, 2 if yellow only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent              # aether/
WORKSPACE_ROOT = ROOT.parent                                # git repo root

# ANSI · shared with all aether CLIs (Day 13 · B-choice follow-up to coll-0084)
# selfcheck uses inline f-string style (e.g. f"{BOLD}...{RESET}") · no `_c()`
# helper to migrate · just swap the constant source. Byte-for-byte output
# unchanged (values match aether_paths exactly).
import aether_paths as _ap                                       # noqa: E402
RED    = _ap.RED
GREEN  = _ap.GREEN
YELLOW = _ap.YELLOW
BLUE   = _ap.BLUE
GRAY   = _ap.GRAY
BOLD   = _ap.BOLD
RESET  = _ap.RESET


@dataclass
class Check:
    layer: str
    name: str
    status: str  # "ok" / "warn" / "fail"
    detail: str = ""
    fix_hint: str = ""

    def symbol(self) -> str:
        return {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}[self.status]

    def color(self) -> str:
        return {"ok": GREEN, "warn": YELLOW, "fail": RED}[self.status]


def check_exists(rel: str, expected_min_bytes: int = 1, base: Path | None = None) -> bool:
    p = (base or ROOT) / rel
    if not p.exists():
        return False
    if p.is_file() and p.stat().st_size < expected_min_bytes:
        return False
    return True


# ─── L0 · File layer ────────────────────────────────────────

def check_l0_files() -> list[Check]:
    checks = []
    critical_aether = [
        "AGENTS.md",
        "README.md",
        "PROJECT-MAP.md",
        "STRATEGY.md",
        "ROADMAP.md",
    ]
    critical_workspace = [
        "LICENSE",
        ".gitignore",
    ]
    missing = [f for f in critical_aether if not check_exists(f, 100)]
    missing += [f for f in critical_workspace if not check_exists(f, 100, base=WORKSPACE_ROOT)]
    if missing:
        checks.append(Check("L0", "critical root files", "fail",
                           f"missing: {', '.join(missing)}",
                           "these must exist for Aether to function"))
    else:
        checks.append(Check("L0", "critical root files", "ok",
                           f"{len(critical_aether) + len(critical_workspace)} files present"))

    # Git status from workspace root (where .git lives)
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=WORKSPACE_ROOT,
                            capture_output=True, text=True, timeout=10)
        modified = len([l for l in out.stdout.splitlines() if l.strip()])
        if modified > 50:
            checks.append(Check("L0", "git uncommitted", "warn",
                               f"{modified} files uncommitted",
                               "consider `git add -A && git commit`"))
        else:
            checks.append(Check("L0", "git uncommitted", "ok",
                               f"{modified} files uncommitted"))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        checks.append(Check("L0", "git", "warn", "git not available", ""))

    return checks


# ─── L1 · Memory layer ──────────────────────────────────────

def check_l1_memory() -> list[Check]:
    checks = []

    memory_files = {
        "labs/chronicle/collaboration-pact-2026-04-17.md": 1000,
        "gen6-noesis/mirror/user-essence.md": 500,
        "docs/30-day-plan.md": 1000,
        "docs/SESSION-HANDSHAKE.md": 500,
    }
    for path, min_size in memory_files.items():
        if check_exists(path, min_size):
            checks.append(Check("L1", Path(path).name, "ok"))
        else:
            checks.append(Check("L1", Path(path).name, "fail",
                               "missing or truncated",
                               "this breaks cross-session memory"))

    # Handshake readiness: rules file has PROTOCOL 0? (lives at workspace root)
    rules = WORKSPACE_ROOT / ".cursor" / "rules" / "aether.mdc"
    if rules.exists():
        text = rules.read_text(encoding="utf-8")
        if "PROTOCOL 0" in text and "handshake" in text.lower():
            checks.append(Check("L1", "handshake protocol", "ok",
                               "PROTOCOL 0 present in aether.mdc"))
        else:
            checks.append(Check("L1", "handshake protocol", "fail",
                               "aether.mdc missing PROTOCOL 0",
                               "cross-session memory won't work"))
    else:
        checks.append(Check("L1", "handshake protocol", "fail",
                           "aether.mdc not found",
                           "Cursor won't load any Aether rules"))

    return checks


# ─── L2 · Field library ─────────────────────────────────────

def check_l2_fields() -> list[Check]:
    checks = []
    fields_dir = ROOT / "gen4-morphogen" / "fields"
    if not fields_dir.exists():
        checks.append(Check("L2", "field library", "fail",
                           "gen4-morphogen/fields/ missing", ""))
        return checks

    active = list(fields_dir.rglob("*.field.md"))
    dormant = list((ROOT / "labs" / "dormant-fields").rglob("*.field.md")) if (ROOT / "labs" / "dormant-fields").exists() else []

    # Required core fields
    required = ["linus-torvalds", "engineering-rigor", "jony-ive",
                "cold-to-warm", "deep-thinking", "brainstorm"]
    active_ids = {p.stem.replace(".field", "") for p in active}
    missing = [r for r in required if r not in active_ids]

    if missing:
        checks.append(Check("L2", "core fields present", "fail",
                           f"missing: {', '.join(missing)}",
                           "these 6 are the minimum for 5-mode system"))
    else:
        checks.append(Check("L2", "core fields", "ok",
                           f"{len(active)} active / {len(dormant)} dormant"))

    # Field file integrity: each field must declare its behavioral shape.
    # Valid shapes (any one is enough):
    #   - 核心浓度向量 / core vector       — standard multi-dim concentration field
    #   - 温度决定的维度 / temperature axis — single-axis temperament fields
    #   - dimension table with explicit | 维度 | column header
    # Old check used `or X and Y` which due to Python operator precedence
    # resolved as `or (X and Y)`, producing false positives on ZH-only fields
    # and on temperament axes.
    malformed = []
    for p in active[:20]:  # sample check
        text = p.read_text(encoding="utf-8")
        text_lc = text.lower()
        has_shape_header = (
            "核心浓度向量" in text
            or "温度决定的维度" in text
            or ("core" in text_lc and "vector" in text_lc)
            or "气质轴" in text
        )
        has_dimension_col = "| 维度 |" in text or "| dimension |" in text_lc
        if not (has_shape_header or has_dimension_col):
            malformed.append(p.stem)
    if malformed:
        checks.append(Check("L2", "field schema", "warn",
                           f"fields without clear vector: {', '.join(malformed[:3])}",
                           "review field file template"))
    else:
        checks.append(Check("L2", "field schema", "ok",
                           "all sampled fields have vectors"))

    return checks


# ─── L3 · Rules layer ───────────────────────────────────────

def check_l3_rules() -> list[Check]:
    checks = []
    rules = WORKSPACE_ROOT / ".cursor" / "rules" / "aether.mdc"

    if not rules.exists():
        checks.append(Check("L3", ".cursor/rules/aether.mdc", "fail",
                           "file does not exist",
                           "Cursor won't inject any Aether context"))
        return checks

    text = rules.read_text(encoding="utf-8")

    if text.startswith("---") and "alwaysApply: true" in text:
        checks.append(Check("L3", "alwaysApply directive", "ok",
                           "frontmatter sets alwaysApply: true"))
    else:
        checks.append(Check("L3", "alwaysApply directive", "fail",
                           "frontmatter missing or alwaysApply: false",
                           "Cursor will not auto-load this rule"))

    if "CODE-REVIEW" in text and "CODE-WRITE" in text and "THINK" in text:
        checks.append(Check("L3", "5-mode table", "ok",
                           "5 modes defined in rules"))
    else:
        checks.append(Check("L3", "5-mode table", "warn",
                           "not all 5 modes found",
                           "add mode table to aether.mdc"))

    if len(text) > 8000:
        checks.append(Check("L3", "rules file size", "warn",
                           f"{len(text)} chars · may exceed token budget",
                           "trim to < 6000 chars for reliable loading"))
    else:
        checks.append(Check("L3", "rules file size", "ok",
                           f"{len(text)} chars"))

    return checks


# ─── L4 · Collapse data ─────────────────────────────────────

def check_l4_collapse() -> list[Check]:
    checks = []

    hot = ROOT / "gen6-noesis" / "collapse-events"
    archive = ROOT / "gen6-noesis" / "archive"

    hot_count = len(list(hot.glob("coll-*.md"))) if hot.exists() else 0
    archive_count = 0
    if archive.exists():
        for q in archive.iterdir():
            if q.is_dir():
                archive_count += len(list(q.glob("coll-*.md")))

    total = hot_count + archive_count

    if total < 10:
        checks.append(Check("L4", "collapse history", "warn",
                           f"only {total} collapses · too sparse for calibrate",
                           "use Aether in real work to generate more"))
    else:
        checks.append(Check("L4", "collapse history", "ok",
                           f"{total} total({hot_count} hot + {archive_count} cold)"))

    # Check index
    if (archive / "index.json").exists():
        checks.append(Check("L4", "archive index", "ok",
                           "index.json present"))
    else:
        checks.append(Check("L4", "archive index", "warn",
                           "no index.json",
                           "run `aether_archive.py --rebuild-index`"))

    # Check integrity baseline
    baseline = ROOT / "labs" / "integrity" / "baseline.json"
    if baseline.exists():
        try:
            data = json.loads(baseline.read_text(encoding="utf-8"))
            checks.append(Check("L4", "integrity baseline", "ok",
                               f"baseline tracks {data.get('total_files', '?')} files"))
        except json.JSONDecodeError:
            checks.append(Check("L4", "integrity baseline", "warn",
                               "baseline.json corrupted"))
    else:
        checks.append(Check("L4", "integrity baseline", "warn",
                           "no baseline",
                           "run `aether_integrity.py --save-baseline`"))

    return checks


# ─── L5 · Evolution layer ───────────────────────────────────

def check_l5_evolution() -> list[Check]:
    checks = []

    # Day 13 form α: gen5-7 and gen6/critique, gen6/evolution-proposals
    # archived to labs/archive-concepts/. L5/L6 scan both old and archive
    # paths so "archived" reports as ok rather than fail/warn.
    archive_root = ROOT / "labs" / "archive-concepts"

    # Critique directory · check old path first, archive path as fallback
    crit_dir = ROOT / "gen6-noesis" / "critique"
    crit_archive = archive_root / "gen6-critique"
    if crit_dir.exists():
        crit_count = len(list(crit_dir.glob("critique-*.md")))
        checks.append(Check("L5", "critique runs", "ok" if crit_count else "warn",
                           f"{crit_count} critiques generated"))
    elif crit_archive.exists():
        crit_count = len(list(crit_archive.glob("critique-*.md")))
        checks.append(Check("L5", "critique runs", "ok",
                           f"archived (form α · Day 13) · {crit_count} historical critiques in labs/archive-concepts/gen6-critique/"))
    else:
        # Form α state: neither live nor archive · acceptable post-cut
        checks.append(Check("L5", "critique runs", "ok",
                           "no critique/ directory · form α · aether_critic archived"))

    # Evolution proposals
    # Bug fix(Day 11 · P0-4 配套): 旧代码用 `"applied_at:" in text` · 会被
    # ep 模板里的 `applied_at: <ISO8601>` 示例字符串误判为 applied。改用
    # 正则匹配真实 ISO 时间值。
    #
    # Day 11 ep-0003 补:`superseded_at:` 同样算已处理(declined 态 · 不是
    # pending · 见 ep-0003)。让 L5 的"未处理"等于"既非 applied · 也未被
    # supersede"。
    _applied_re = re.compile(r"^applied_at:\s*\d{4}-\d{2}-\d{2}T", re.MULTILINE)
    _superseded_re = re.compile(r"^[-\s]*`?superseded_at:?`?\s*:?\s*\d{4}-\d{2}-\d{2}T", re.MULTILINE)

    def _ep_is_processed(text: str) -> bool:
        return bool(_applied_re.search(text) or _superseded_re.search(text))

    ep_dir = ROOT / "gen6-noesis" / "evolution-proposals"
    ep_archive = archive_root / "gen6-evolution-proposals"
    # Prefer live dir; fall back to archive (form α).
    active_ep_dir = ep_dir if ep_dir.exists() else (ep_archive if ep_archive.exists() else None)
    if active_ep_dir is not None:
        eps = list(active_ep_dir.glob("ep-*.md"))
        applied_n = 0
        superseded_n = 0
        pending: list = []
        for p in eps:
            text = p.read_text(encoding="utf-8")
            if _applied_re.search(text):
                applied_n += 1
            elif _superseded_re.search(text):
                superseded_n += 1
            else:
                pending.append(p)
        archived_note = " (archived · form α · Day 13)" if active_ep_dir is ep_archive else ""
        if pending:
            checks.append(Check("L5", "evolution proposals", "warn",
                               f"{len(pending)} unapplied proposals backlogged"
                               f" ({applied_n} applied · {superseded_n} superseded){archived_note}",
                               f"review: {pending[0].name}"))
        elif eps:
            checks.append(Check("L5", "evolution proposals", "ok",
                               f"{len(eps)} proposals · {applied_n} applied · {superseded_n} superseded · 0 pending{archived_note}"))
        else:
            # Archive exists but is empty · form α stable state
            checks.append(Check("L5", "evolution proposals", "ok",
                               f"no ep-*.md yet{archived_note} · form α"))
    else:
        # Neither live nor archive · form α stable state
        checks.append(Check("L5", "evolution proposals", "ok",
                           "no evolution-proposals/ · form α · aether_evolve archived"))

    # Preference calibration
    cal = ROOT / "gen6-noesis" / "mirror" / "preference-calibration.md"
    if cal.exists():
        checks.append(Check("L5", "preference calibration", "ok",
                           "calibration report present"))
    else:
        checks.append(Check("L5", "preference calibration", "warn",
                           "no calibration report",
                           "run `aether_calibrate.py`"))

    return checks


# ─── L6 · Species layer ─────────────────────────────────────

def check_l6_species() -> list[Check]:
    checks = []

    # Day 13 form α: gen5-ecoware archived to labs/archive-concepts/gen5-ecoware/
    # L6 resolves registry path first from the archive (if moved) then from
    # original location. "archived" is a valid ok state · not a failure.
    archive_root = ROOT / "labs" / "archive-concepts" / "gen5-ecoware"
    archived = archive_root.exists()

    reg_orig = ROOT / "gen5-ecoware" / "species-registry.json"
    reg_arch = archive_root / "species-registry.json"
    reg = reg_orig if reg_orig.exists() else (reg_arch if reg_arch.exists() else None)

    if reg is None:
        # Template OK?
        tmpl_orig = ROOT / "gen5-ecoware" / "species-registry.template.json"
        tmpl_arch = archive_root / "species-registry.template.json"
        tmpl = tmpl_orig if tmpl_orig.exists() else (tmpl_arch if tmpl_arch.exists() else None)
        if archived and tmpl is not None:
            # gen5 archived + template still present = form α healthy state
            checks.append(Check("L6", "species registry", "ok",
                               "archived (form α · Day 13) · template preserved in labs/archive-concepts/gen5-ecoware/"))
            return checks
        if tmpl is not None:
            checks.append(Check("L6", "species registry", "warn",
                               "only template exists · no actual registry",
                               "copy template to species-registry.json"))
        else:
            checks.append(Check("L6", "species registry", "fail",
                               "neither registry nor template",
                               "ecosystem layer broken"))
        return checks

    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        checks.append(Check("L6", "species registry", "fail",
                           "registry.json malformed",
                           "recover from template"))
        return checks

    species = {k: v for k, v in data.get("species", {}).items() if not k.startswith("_")}
    gen = data.get("generation", 0)
    archived_note = " (archived · form α · Day 13)" if archived else ""
    checks.append(Check("L6", "species count", "ok",
                       f"Generation {gen} · {len(species)} species registered{archived_note}"))

    # Nursery · same archive-aware resolution
    nursery_orig = ROOT / "gen5-ecoware" / "nursery"
    nursery_arch = archive_root / "nursery"
    nursery = nursery_orig if nursery_orig.exists() else (nursery_arch if nursery_arch.exists() else None)
    seeds = list(nursery.glob("*.seed.md")) if nursery else []
    ready: list = []
    for s in seeds:
        try:
            t = s.read_text(encoding="utf-8")
        except OSError:
            continue
        if "ripe-for-promotion" in t or "ready-for-promotion" in t:
            ready.append(s)
    if ready:
        checks.append(Check("L6", "ripe seeds",
                           "ok" if archived else "warn",
                           f"{len(ready)} seed(s) ripe for promotion{archived_note}",
                           None if archived else "run `python aether/bin/aether_promote.py` to graduate them"))
    else:
        checks.append(Check("L6", "nursery", "ok",
                           f"{len(seeds)} seeds ripening{archived_note}"))

    return checks


# ─── L7 · CLI tool layer ────────────────────────────────────

def check_l7_cli() -> list[Check]:
    checks = []
    bin_dir = ROOT / "bin"

    if not bin_dir.exists():
        checks.append(Check("L7", "bin/", "fail", "bin/ not found"))
        return checks

    py_tools = list(bin_dir.glob("aether_*.py")) + [bin_dir / "aether.py"]
    py_tools = [p for p in py_tools if p.exists()]

    # Day 13 form α:
    # - "expected" list rewritten to the 10 keep-list + critical support CLIs
    # - gen5-7 specific CLIs (critic / evolve / promote / seeds) moved to
    #   labs/archive-cli/ · no longer in daily keep list · but we verify the
    #   archive exists so users who want to revive can find them
    missing_tools = []
    expected = [
        # 10 core keep (Day 12 handover · form α)
        "aether_install.py", "aether_hook.py", "aether_handshake.py",
        "aether_paths.py", "aether_tasks.py", "aether_daily.py",
        "aether_doctor.py", "aether_selfcheck.py", "aether_query.py",
        "aether_events.py",
        # Support CLIs still active (not in the Day 13 archive cut)
        "aether_guardian.py", "aether_indexer.py", "aether_project.py",
        "aether_federate.py", "aether_session_summarizer.py",
        "aether_stats.py", "aether_integrity.py", "aether_snapshot.py",
        "aether_archive.py", "aether_autopilot.py",
    ]
    for e in expected:
        if not (bin_dir / e).exists():
            missing_tools.append(e)

    # Also verify the archived CLIs are preserved (can be revived)
    archived_cli_dir = ROOT.parent.parent / "aether" / "labs" / "archive-cli"
    if not archived_cli_dir.exists():
        # Fallback: the cli dir might be under ROOT directly if this file moves
        archived_cli_dir = ROOT / "labs" / "archive-cli"
    archive_note = ""
    if archived_cli_dir.exists():
        archived_count = len(list(archived_cli_dir.glob("aether_*.py")))
        archive_note = f" · {archived_count} CLIs archived in labs/archive-cli/"

    if missing_tools:
        checks.append(Check("L7", "CLI tools present", "fail",
                           f"missing: {', '.join(missing_tools)}",
                           "reinstall from git"))
    else:
        checks.append(Check("L7", "CLI tools present", "ok",
                           f"{len(py_tools)} tools in bin/{archive_note}"))

    # deploy.ps1 present?
    if (bin_dir / "deploy.ps1").exists():
        checks.append(Check("L7", "deploy script", "ok"))
    else:
        checks.append(Check("L7", "deploy script", "warn",
                           "bin/deploy.ps1 missing"))

    return checks


# ─── L8 · Publish layer ─────────────────────────────────────

def check_l8_publish() -> list[Check]:
    checks = []
    site = ROOT / "site"
    if not site.exists():
        checks.append(Check("L8", "site/ directory", "fail",
                           "Astro project missing"))
        return checks

    # Package.json
    pkg = site / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            if "astro" in data.get("dependencies", {}):
                checks.append(Check("L8", "astro project", "ok",
                                   f"astro {data['dependencies']['astro']}"))
            else:
                checks.append(Check("L8", "astro project", "warn",
                                   "no astro in dependencies"))
        except json.JSONDecodeError:
            checks.append(Check("L8", "package.json", "fail", "malformed"))
    else:
        checks.append(Check("L8", "package.json", "fail", "missing"))

    # i18n pages present?
    zh = len(list((site / "src" / "pages" / "zh").glob("*.astro"))) if (site / "src" / "pages" / "zh").exists() else 0
    en = len(list((site / "src" / "pages" / "en").glob("*.astro"))) if (site / "src" / "pages" / "en").exists() else 0
    if zh == en and zh >= 4:
        checks.append(Check("L8", "bilingual parity", "ok",
                           f"{zh} zh pages = {en} en pages"))
    else:
        checks.append(Check("L8", "bilingual parity", "warn",
                           f"zh={zh} · en={en} · asymmetric",
                           "i18n unbalanced · mirror missing pages"))

    # Stats file present?
    if (site / "public" / "stats.json").exists():
        checks.append(Check("L8", "live stats.json", "ok"))
    else:
        checks.append(Check("L8", "live stats.json", "warn",
                           "no stats.json",
                           "run `aether_stats.py`"))

    return checks


# ─── L10 · Hooks coverage ──────────────────────────────────

def check_l10_hooks() -> list[Check]:
    """Layer C reflex arc · hooks.json registration + payload schema audit.

    Two checks · together they answer: 'is the C-layer doing its job ·
    are we leaving Cursor data on the table?'

      1. Hook count · we know there are 18 official events. We don't need
         all 18 (some are Tab-only · some require shell sandboxing) but if
         we drop below 6 the reflex arc is degraded · warn.
      2. Payload schema unused fields · `aether_payload_schema.py --check`
         reports any field present in real Cursor samples but not in our
         KNOWN_CONSUMED_FIELDS whitelist. Each unused field = AI flying
         blind on that piece of telemetry. Warn at 1+ · fail at 3+.
    """
    checks: list[Check] = []
    hooks_json = WORKSPACE_ROOT / ".cursor" / "hooks.json"
    schema_tool = ROOT / "bin" / "aether_payload_schema.py"

    # 10.1 · hooks.json registration count
    if not hooks_json.exists():
        checks.append(Check("L10", "hooks.json", "fail",
                            ".cursor/hooks.json missing",
                            "restore hooks config · without it C-layer reflex is dead"))
        return checks
    try:
        cfg = json.loads(hooks_json.read_text(encoding="utf-8"))
        registered = list(cfg.get("hooks", {}).keys())
    except Exception as e:
        checks.append(Check("L10", "hooks.json", "fail",
                            f"hooks.json malformed: {e}",
                            "fix JSON syntax · selfcheck can't audit reflex"))
        return checks

    n = len(registered)
    OFFICIAL_EVENT_COUNT = 18
    pct = int(n / OFFICIAL_EVENT_COUNT * 100)
    if n >= 9:
        checks.append(Check("L10", "hook coverage", "ok",
                            f"{n}/{OFFICIAL_EVENT_COUNT} events ({pct}%) · {', '.join(registered)}"))
    elif n >= 5:
        checks.append(Check("L10", "hook coverage", "warn",
                            f"{n}/{OFFICIAL_EVENT_COUNT} events ({pct}%) · "
                            f"reflex arc partially deployed",
                            "consider afterAgentResponse · preCompact · "
                            "postToolUseFailure · beforeShellExecution"))
    else:
        checks.append(Check("L10", "hook coverage", "fail",
                            f"only {n}/{OFFICIAL_EVENT_COUNT} events registered · "
                            f"reflex arc severely degraded",
                            "see aether/docs/hook-payload-schema.md for guidance"))

    # 10.2 · payload schema unused fields
    if not schema_tool.exists():
        checks.append(Check("L10", "payload schema audit", "warn",
                            "aether_payload_schema.py missing",
                            "restore tool to enable unused-field detection"))
        return checks

    try:
        r = subprocess.run(
            [sys.executable, str(schema_tool), "--json"],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
        )
        rep = json.loads(r.stdout)
    except Exception as e:
        checks.append(Check("L10", "payload schema audit", "warn",
                            f"schema audit failed: {e}",
                            "run `python bin/aether_payload_schema.py` manually"))
        return checks

    unused = rep.get("unused_field_count", 0)
    events_seen = len(rep.get("events", {}))
    if events_seen == 0:
        checks.append(Check("L10", "payload schema audit", "warn",
                            "no Cursor hook samples yet (.cursor/hooks/.discovery/ empty)",
                            "restart Cursor to let hooks generate samples"))
    elif unused == 0:
        checks.append(Check("L10", "payload schema audit", "ok",
                            f"{events_seen} events scanned · 0 unused fields"))
    elif unused < 3:
        unused_by = rep.get("unused_by_event", {})
        bits = ", ".join(f"{ev}:{','.join(fs[:2])}" for ev, fs in list(unused_by.items())[:3])
        checks.append(Check("L10", "payload schema audit", "warn",
                            f"{unused} unused field(s) · {bits}",
                            "see aether/docs/hook-payload-schema.md · "
                            "consume them in aether_hook.py + add to KNOWN_CONSUMED_FIELDS"))
    else:
        unused_by = rep.get("unused_by_event", {})
        bits = ", ".join(f"{ev}:{','.join(fs[:2])}" for ev, fs in list(unused_by.items())[:3])
        checks.append(Check("L10", "payload schema audit", "fail",
                            f"{unused} unused field(s) across {len(unused_by)} events · {bits}",
                            "data being silently dropped · consume or whitelist now"))

    return checks


# ─── L11 · Day N consistency ───────────────────────────────
#
# Day 10 session 5 (coll-0089) 发现 AI 在一个 session 内自编 "Day 13/14/15/17"
# · 偏离 handshake.current_day() 推算的真实 Day。根因: Day N 没有 selfcheck
# 兜底 · AI 不读 status line 系统也不报错。L11 在 Day 11 落地(本次 Owner
# reality-check P0-4 · 兑现 PATH-RESOLUTION-SPEC 附录 C 留下的伪码)。
#
# 检查项:
#   11.1 · 最新 handover 的编号 + 1 = current_day 应该返回值(sanity)
#   11.2 · 最近 3 个 coll 的 Date 字段解析出的 "Day N" · 与 latest_handover
#          的 N+1 对比 · 差距 > 2 视为 drift(允许跨 session 的小偏移)
#   11.3 · latest open tasks 的 `day` 字段 · 同 11.2 阈值
#
# 设计哲学: L11 是 "数据 vs 算法权威" 的 regression guard · 不是 enforcement。
# fail 不代表系统坏了 · 代表 AI 在写 coll/task 时可能没读 status line。

_DAY_N_DRIFT_WARN = 2
_DAY_N_DRIFT_FAIL = 5

def _parse_day_from_coll_date(text: str) -> int | None:
    """Extract Day N from a coll front-matter 'Date' field.

    Matches patterns like:
      **Date**: 2026-04-22 · **Day 10 · session 5**(本 session 第 5 个 coll)
      **Date**: 2026-04-22 · Day 11
    Returns None when no Day number found.
    """
    m = re.search(r"\*\*Date\*\*:\s*[^\n]*?Day\s+(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def check_l11_day_consistency(overlay_dir: Path | None = None) -> list[Check]:
    """L11 · Day N consistency check · scope-aware (Day 12 · coll-0092).

    When `overlay_dir=None` (default) · reads central's docs/daily/,
    gen6-noesis/collapse-events/, and .aether/tasks.jsonl · same as before.

    When `overlay_dir` is supplied (future `--overlay` mode) · reads
    overlay/handover/, overlay/coll/, and overlay/tasks.jsonl · giving
    guest projects their own Day N drift guard.

    Backwards compatible: existing callers that do `check_l11_day_consistency()`
    keep getting central-scoped checks. No behavior change for dev-self.
    """
    checks: list[Check] = []

    # Resolve sources (overlay-aware · Day 12 addition)
    if overlay_dir is not None:
        daily = overlay_dir / "handover"
        coll_dir = overlay_dir / "coll"
        tasks_path = overlay_dir / "tasks.jsonl"
    else:
        daily = ROOT / "docs" / "daily"
        coll_dir = ROOT / "gen6-noesis" / "collapse-events"
        tasks_path = WORKSPACE_ROOT / ".aether" / "tasks.jsonl"

    # 11.1 · latest handover number
    handovers = list(daily.glob("day-*-handover.md")) if daily.exists() else []

    def day_num(p):
        m = re.match(r"day-(\d+)-handover\.md", p.name)
        return int(m.group(1)) if m else -1

    if not handovers:
        checks.append(Check("L11", "handover presence", "warn",
                            "no day-*-handover.md · status line will fallback",
                            "write end-of-day handover so Day N can advance"))
        return checks

    max_handover = max(day_num(p) for p in handovers)
    expected_day = max_handover + 1
    checks.append(Check("L11", "latest handover", "ok",
                        f"day-{max_handover}-handover.md → session Day {expected_day}"))

    # 11.2 · recent coll Day drift
    if coll_dir.exists():
        recent = sorted(coll_dir.glob("coll-*.md"), reverse=True)[:3]
        drifts: list[tuple[str, int, int]] = []
        for cp in recent:
            try:
                text = cp.read_text(encoding="utf-8", errors="replace")[:2000]
                d = _parse_day_from_coll_date(text)
            except OSError:
                continue
            if d is None:
                continue
            # coll writes Day N for the session they happened in · expected
            # range is [max_handover, expected_day] (a coll in Day N's session
            # belongs to Day N · and Day N = max_handover when handover isn't
            # written yet · or = expected_day after handover exists).
            if d < max_handover - _DAY_N_DRIFT_WARN or d > expected_day + _DAY_N_DRIFT_WARN:
                drifts.append((cp.stem, d, expected_day))
        if not drifts:
            checks.append(Check("L11", "recent coll Day N", "ok",
                                f"last {len(recent)} coll(s) Day N within tolerance"))
        else:
            # Determine severity · first drift's distance decides
            max_dist = max(abs(d - expected_day) for _, d, _ in drifts)
            bits = ", ".join(f"{c}(Day {d} vs ~{exp})" for c, d, exp in drifts[:3])
            status = ("fail" if max_dist >= _DAY_N_DRIFT_FAIL
                      else "warn")
            checks.append(Check("L11", "coll Day N drift", status,
                                f"{len(drifts)} coll(s) with Day N drift · {bits}",
                                "AI may have self-authored Day N · AGENTS §3.7 · "
                                "read status line instead"))

    # 11.3 · open tasks Day drift
    #
    # Semantics: task `day` 字段 = 该 task 被创建的那一天(AGENTS §3.7)·
    # 而非"目标完成日"。所以 `day > current_day` 不是漂移 · 是未来占位
    # task(P2/P3 常见 · 如 "Day 30 评估 PyPI")· 允许。
    #
    # 只对 `day < current_day - _DAY_N_DRIFT_WARN` 的 open task 报 drift ·
    # 因为:
    #   · task 创建于过去 · 且 day 字段小于合理范围 = 可能 AI 自编 Day N
    #     污染 · 或者 task 被忘记 close(stale)· 这两种都该看一眼。
    # 额外:P2/P3 的未来 task 不在检查范围(长期债 · 不是当日 task)。
    # tasks_path already resolved at function top (overlay-aware · Day 12)
    if tasks_path.exists():
        try:
            drifts_t: list[tuple[str, int, str]] = []
            with open(tasks_path, "r", encoding="utf-8", errors="replace") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        t = json.loads(ln)
                    except json.JSONDecodeError:
                        continue
                    if t.get("status") != "open":
                        continue
                    d = t.get("day")
                    if not isinstance(d, int):
                        continue
                    prio = t.get("priority", "")
                    # 只检 P0 / P1 的过去漂移 · P2 / P3 允许长期占位
                    if prio in ("P2", "P3"):
                        continue
                    # 只对 past drift 报(day < current_day - tolerance)
                    if d < max_handover - _DAY_N_DRIFT_WARN:
                        drifts_t.append((t.get("id", "?"), d, prio))
            if not drifts_t:
                checks.append(Check("L11", "open tasks Day N", "ok"))
            else:
                max_dist_t = max(abs(d - expected_day) for _, d, _ in drifts_t)
                bits = ", ".join(f"{tid}({prio}, Day {d})" for tid, d, prio in drifts_t[:3])
                status = ("fail" if max_dist_t >= _DAY_N_DRIFT_FAIL else "warn")
                checks.append(Check("L11", "task Day N drift", status,
                                    f"{len(drifts_t)} P0/P1 task(s) with past-drift · {bits}",
                                    "run `aether tasks audit` · close stale or fix day field"))
        except OSError:
            pass

    return checks


# ─── L9 · Tasks ledger ─────────────────────────────────────

def check_l9_tasks() -> list[Check]:
    """Layer A · jsonl task ledger.

    Distinguishes 'system feels healthy' (file structure) from 'work is
    actually getting done' (task throughput). Stale-task penalty bleeds
    into the overall score so 100/100 means more than just file presence.
    """
    checks: list[Check] = []
    tasks_path = WORKSPACE_ROOT / ".aether" / "tasks.jsonl"
    tasks_tool = ROOT / "bin" / "aether_tasks.py"

    if not tasks_tool.exists():
        checks.append(Check("L9", "tasks tool", "fail",
                            "aether_tasks.py missing",
                            "restore from coll-0071 · build the ledger"))
        return checks

    if not tasks_path.exists():
        checks.append(Check("L9", "tasks ledger", "warn",
                            ".aether/tasks.jsonl not yet created",
                            "run `python bin/aether_tasks.py add P0 ...` to seed"))
        return checks

    # Delegate audit to the tasks tool · respects the canonical thresholds
    try:
        r = subprocess.run(
            [sys.executable, str(tasks_tool), "audit", "--json"],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
        )
        rep = json.loads(r.stdout)
    except Exception as e:
        checks.append(Check("L9", "tasks audit", "fail",
                            f"audit failed: {e}",
                            "check aether_tasks.py audit manually"))
        return checks

    total = rep.get("total_open_count", 0)
    fresh = rep.get("fresh_open_count", 0)
    stale_count = rep.get("stale_count", 0)
    penalty = rep.get("health_penalty", 0)

    if stale_count == 0:
        checks.append(Check("L9", "open tasks", "ok",
                            f"{total} open · {fresh} fresh · 0 stale"))
    else:
        # Surface each stale id so the operator (you) sees what's overdue
        stale_titles = ", ".join(
            f"{s['id']}({s['priority']}, {s['age_days']}d)"
            for s in rep.get("stale", [])[:5]
        )
        status = "fail" if any(s["priority"] == "P0" for s in rep.get("stale", [])) else "warn"
        checks.append(Check("L9", "open tasks", status,
                            f"{stale_count} stale · -{penalty} health · {stale_titles}",
                            "close · defer · or drop these — see "
                            "`python bin/aether_tasks.py audit`"))
    return checks


# ─── Render ────────────────────────────────────────────────

def render(all_checks: list[Check], json_mode: bool = False):
    if json_mode:
        print(json.dumps([
            {"layer": c.layer, "name": c.name, "status": c.status,
             "detail": c.detail, "fix": c.fix_hint}
            for c in all_checks
        ], ensure_ascii=False, indent=2))
        return

    # Group by layer
    by_layer: dict[str, list[Check]] = {}
    for c in all_checks:
        by_layer.setdefault(c.layer, []).append(c)

    layer_names = {
        "L0": "Files",
        "L1": "Memory",
        "L2": "Fields",
        "L3": "Rules",
        "L4": "Collapse",
        "L5": "Evolution",
        "L6": "Species",
        "L7": "CLI",
        "L8": "Publish",
        "L9": "Tasks",
        "L10": "Hooks",
        "L11": "DayN",
    }

    print()
    print(f"{BOLD}⟁ Aether Self-Check · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}{RESET}")
    print("─" * 64)

    for layer_key in sorted(by_layer.keys()):
        layer_checks = by_layer[layer_key]
        layer_name = layer_names.get(layer_key, layer_key)
        statuses = [c.status for c in layer_checks]
        layer_status = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "ok")
        color = {"ok": GREEN, "warn": YELLOW, "fail": RED}[layer_status]

        print()
        print(f"{color}━━ {layer_key} · {layer_name}{RESET}")
        for c in layer_checks:
            marker = c.color() + c.symbol() + RESET
            print(f"  {marker}  {c.name:28s}  {GRAY}{c.detail}{RESET}")
            if c.fix_hint and c.status != "ok":
                print(f"       {YELLOW}↳ fix: {c.fix_hint}{RESET}")

    # Summary
    total = len(all_checks)
    ok = sum(1 for c in all_checks if c.status == "ok")
    warn = sum(1 for c in all_checks if c.status == "warn")
    fail = sum(1 for c in all_checks if c.status == "fail")
    score = int(ok / total * 100)

    print()
    print("─" * 64)
    health = "🟢 HEALTHY" if fail == 0 and warn <= 2 else ("🟡 NEEDS ATTENTION" if fail == 0 else "🔴 CRITICAL ISSUES")
    print(f"{BOLD}Overall: {health} · {score}/100 · {ok} OK · {warn} warn · {fail} fail{RESET}")
    print()


def _autopilot_tick() -> None:
    """Lazy-trigger guardian if the index is stale. Silent · non-blocking."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from aether_autopilot import maybe_trigger_ingest
        maybe_trigger_ingest()
    except Exception:
        pass


# ─── Honesty layer · Owner P1-8 · Day 11 reality-check ────
#
# 常规 selfcheck(L0-L11) 测的是"装潢是否齐全"· 不测"产品是否有人用"。
# 0 外部用户 + 0 付费 + 100% 自我指涉 coll · 照样能打 96/100 · 这是
# 本 Day 11 Owner reality-check 发现的最核心 bug(L6 的 diversity=1.0 是
# 数学错误 · 同一原理 · 指标设计让"完备"=所有 check OK · 但"完备"可以
# 独立于"有价值"成立)。
#
# `--honest` flag 加一层 "utility checks" · 覆盖真价值指标:
#   · 外部 GitHub stars (stats.json · 硬外部信号)
#   · 付费用户 (当前没有机制 · 返回 0 + fix hint)
#   · 非自我指涉 coll 占比(grep 最近 10 个 coll 的主题词)
#   · Pro fields 数
#   · ep applied 次数
#   · species count > 1 (monoculture detection)
#
# 默认不跑 · 因为 Owner 有时候只想看装潢是否 OK · 不想每次都被"0 用户"
# 数字打脸。`--honest` 是 opt-in 的诚实凝视。

def _honest_utility_checks() -> list[Check]:
    checks: list[Check] = []

    # Utility 1 · stars from live stats
    stats_path = ROOT / "site" / "public" / "stats.json"
    stars = 0
    if stats_path.exists():
        try:
            data = json.loads(stats_path.read_text(encoding="utf-8"))
            stars = int(data.get("github", {}).get("stars") or 0)
        except Exception:
            stars = 0
    if stars >= 50:
        checks.append(Check("HON", "github stars", "ok", f"{stars} stars"))
    elif stars >= 10:
        checks.append(Check("HON", "github stars", "warn",
                            f"{stars} stars · below Day 30 target 50"))
    else:
        checks.append(Check("HON", "github stars", "fail",
                            f"{stars} stars · no external traction yet",
                            "Day 30 kill criteria requires ≥ 50"))

    # Utility 2 · paying users (no mechanism → 0)
    checks.append(Check("HON", "paying users", "fail",
                        "0 paying users · no purchase flow exists",
                        "add payment link to pro-fields/README.md (GitHub Sponsor / WeChat)"))

    # Utility 3 · non-self-referential coll rate
    # coll-events dir stays live (form α keeps chronicle)
    coll_dir = ROOT / "gen6-noesis" / "collapse-events"
    if coll_dir.exists():
        recent = sorted(coll_dir.glob("coll-*.md"), reverse=True)[:10]
        # "self-referential" heuristic: coll body 包含 Aether 自身架构/代码
        # 词汇 ≥ 2 个 · 且不包含 "用 Aether 做 X" 外部用例词汇
        self_ref_words = [
            "aether_", "gen4-morphogen", "gen5-ecoware", "gen6-noesis",
            "handshake", "hook", "overlay", "coll-", "species-registry",
            "SPEC", "selfcheck", "PROTOCOL 0", "field_id", "critic",
        ]
        external_words = [
            "用户问了", "帮用户写", "为客户", "production incident",
            "external user", "customer", "debug 生产",
        ]
        self_ref_count = 0
        external_count = 0
        for cp in recent:
            try:
                text = cp.read_text(encoding="utf-8", errors="replace")[:8000]
            except OSError:
                continue
            s = sum(1 for w in self_ref_words if w in text)
            e = sum(1 for w in external_words if w in text)
            if e >= 1:
                external_count += 1
            elif s >= 2:
                self_ref_count += 1
        n = len(recent)
        if n == 0:
            checks.append(Check("HON", "coll self-referential rate", "warn",
                                "no coll to sample"))
        else:
            ratio = self_ref_count / n
            ext_ratio = external_count / n
            if ext_ratio >= 0.30:
                checks.append(Check("HON", "coll external-task rate", "ok",
                                    f"{external_count}/{n} coll about external tasks"))
            elif self_ref_count == n:
                checks.append(Check("HON", "coll self-referential rate", "fail",
                                    f"{n}/{n} recent coll are Aether-about-Aether",
                                    "reality-check-gen1.md 诊断 · 10 天 0 改善"))
            else:
                checks.append(Check("HON", "coll self-referential rate", "warn",
                                    f"{self_ref_count}/{n} self-ref · {external_count}/{n} external",
                                    "target: ≥ 30% external-task coll"))

    # Utility 4 · Pro fields
    # Day 13 form α: pro-fields archived to labs/archive-concepts/pro-fields.
    # Under form α there is no Pro tier · so this check reports as N/A·archived.
    pro_dir_live = ROOT / "gen4-morphogen" / "pro-fields"
    pro_dir_archive = ROOT / "labs" / "archive-concepts" / "pro-fields"
    pro_dir = pro_dir_live if pro_dir_live.exists() else (
        pro_dir_archive if pro_dir_archive.exists() else None
    )
    if pro_dir is not None:
        pros = [p for p in pro_dir.glob("*.field.md")]
        archived_note = " (archived · form α · Day 13)" if pro_dir is pro_dir_archive else ""
        if archived_note:
            # Under form α no pro tier · do not fail on low count · just note
            checks.append(Check("HON", "pro field count", "ok",
                                f"{len(pros)} pro fields{archived_note} · no Pro tier under form α"))
        elif len(pros) >= 5:
            checks.append(Check("HON", "pro field count", "ok",
                                f"{len(pros)} pro fields"))
        elif len(pros) >= 2:
            checks.append(Check("HON", "pro field count", "warn",
                                f"{len(pros)} pro fields · need ≥ 5 for $99/yr credibility"))
        else:
            checks.append(Check("HON", "pro field count", "fail",
                                f"only {len(pros)} pro field(s)",
                                "at least 3-4 fields needed to justify Pro tier pricing"))

    # Utility 5 · ep applied count(区分"真演化"vs"supersede 决策")
    #
    # HON 问的是:Aether 的**演化闭环**(critic → ep → apply → 指标改善)
    # 真闭合了几次。ep-0003 是"supersede ep-0001"的决策档案 · 有 applied_at
    # 但**没真改 field** · 所以不算演化。判别:metadata 里有 `supersedes:`
    # 字段 = 纯决策 · 不算 applied。
    # Day 13 form α: evolution-proposals archived · check archive path too
    ep_dir_live = ROOT / "gen6-noesis" / "evolution-proposals"
    ep_dir_archive = ROOT / "labs" / "archive-concepts" / "gen6-evolution-proposals"
    ep_dir = ep_dir_live if ep_dir_live.exists() else (
        ep_dir_archive if ep_dir_archive.exists() else None
    )
    real_applied = 0
    decision_only = 0
    total_ep = 0
    _applied_re = re.compile(r"^applied_at:\s*\d{4}-\d{2}-\d{2}T", re.MULTILINE)
    _supersedes_re = re.compile(r"^supersedes:\s*ep-", re.MULTILINE)
    if ep_dir is not None:
        for ep in ep_dir.glob("ep-*.md"):
            total_ep += 1
            try:
                text = ep.read_text(encoding="utf-8", errors="replace")
                if _applied_re.search(text):
                    if _supersedes_re.search(text):
                        decision_only += 1
                    else:
                        real_applied += 1
            except OSError:
                pass
    archived_note = " (archived · form α · Day 13)" if ep_dir is ep_dir_archive else ""
    if archived_note:
        # Under form α · evolution loop archived · report factual without scoring fail
        checks.append(Check("HON", "evolution applied", "ok",
                            f"{real_applied} real evolve applied ({decision_only} decision-only){archived_note} · loop archived"))
    elif real_applied >= 3:
        checks.append(Check("HON", "evolution applied", "ok",
                            f"{real_applied} real evolve applied ({decision_only} decision-only) · pattern"))
    elif real_applied >= 1:
        checks.append(Check("HON", "evolution applied", "warn",
                            f"{real_applied} real evolve applied ({decision_only} decision-only) · "
                            f"n={real_applied} is anecdote · need ≥ 3 for pattern"))
    else:
        checks.append(Check("HON", "evolution applied", "fail",
                            f"0/{total_ep} real evolve applied · evolution loop hasn't closed"))

    # Utility 6 · species monoculture
    # Day 13 form α: gen5-ecoware archived · species concept retired
    reg_live = ROOT / "gen5-ecoware" / "species-registry.json"
    reg_archive = ROOT / "labs" / "archive-concepts" / "gen5-ecoware" / "species-registry.json"
    reg = reg_live if reg_live.exists() else (reg_archive if reg_archive.exists() else None)
    if reg is not None:
        try:
            data = json.loads(reg.read_text(encoding="utf-8"))
            sp = [k for k in data.get("species", {}) if not k.startswith("_")]
            archived_note = " (archived · form α · Day 13)" if reg is reg_archive else ""
            if archived_note:
                # Form α · species concept retired · don't score
                checks.append(Check("HON", "species diversity", "ok",
                                    f"{len(sp)} species{archived_note} · concept retired"))
            elif len(sp) >= 3:
                checks.append(Check("HON", "species diversity", "ok",
                                    f"{len(sp)} species"))
            elif len(sp) == 1:
                checks.append(Check("HON", "species diversity", "fail",
                                    "1 species since Day 1 · monoculture · no emergence",
                                    "nursery has 13 seeds · 0 promoted in 10+ days · "
                                    "either lower promotion threshold or deprecate gen5-ecoware"))
            else:
                checks.append(Check("HON", "species diversity", "warn",
                                    f"{len(sp)} species"))
        except Exception:
            pass

    return checks


def main() -> int:
    _autopilot_tick()
    ap = argparse.ArgumentParser(description="Aether end-to-end architecture health check.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fix", action="store_true", help="(future) auto-fix safe issues")
    ap.add_argument("--honest", action="store_true",
                    help="also run 'utility checks' (external users / paying / "
                         "non-self-referential coll rate) · Day 11 reality-check · "
                         "装潢分(L0-L11) vs 有用性分(这个 flag)分开")
    args = ap.parse_args()

    all_checks: list[Check] = []
    for fn in [check_l0_files, check_l1_memory, check_l2_fields,
               check_l3_rules, check_l4_collapse, check_l5_evolution,
               check_l6_species, check_l7_cli, check_l8_publish,
               check_l9_tasks, check_l10_hooks, check_l11_day_consistency]:
        try:
            all_checks.extend(fn())
        except Exception as e:
            all_checks.append(Check(fn.__name__, "exception", "fail", str(e)))

    if args.honest:
        all_checks.extend(_honest_utility_checks())

    render(all_checks, json_mode=args.json)

    has_fail = any(c.status == "fail" for c in all_checks)
    has_warn = any(c.status == "warn" for c in all_checks)
    return 0 if not has_fail and not has_warn else (1 if has_fail else 2)


if __name__ == "__main__":
    sys.exit(main())
