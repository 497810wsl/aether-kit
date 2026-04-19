#!/usr/bin/env python3
"""
aether · Post-Skill Architecture CLI
====================================

Zero-dependency Python stdlib tool for bootstrapping and operating an Aether
workspace inside any project. Works offline after first fetch.

Usage:
    aether init [--integration cursor|claude|generic] [--force]
    aether fetch <field-id> [--from <url>]
    aether list [--type style|discipline|temperament|all]
    aether collapse "<summary>" --fields "id1=0.8,id2=0.6" [--reaction pos|neg|neutral]
    aether status
    aether link
    aether doctor
    aether version

See docs/USAGE-MODEL.md in the Aether repo for the big picture.

License: MIT · https://github.com/497810wsl/aether
Contact: WeChat wsl497810
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

AETHER_VERSION = "0.4.3-kit"
ONTOLOGY_VERSION = 1
DEFAULT_CORE_REPO = "https://raw.githubusercontent.com/497810wsl/aether-kit/main"
STARTER_PRESET_FIELDS = ["linus-torvalds", "engineering-rigor", "jony-ive"]
AETHER_DIR = ".aether"
CURSOR_RULES_DIR = ".cursor/rules"
CURSOR_RULE_FILE = "aether.mdc"

FORBIDDEN_TERMS = [
    "创建 skill",
    "调用 skill",
    "删除 skill",
    "skill 版本升级",
]

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def short_hash(text: str, length: int = 10) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def nanoid(prefix: str = "", length: int = 8) -> str:
    import secrets

    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    body = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}{body}" if prefix else body


def say(msg: str, kind: str = "info") -> None:
    prefix = {
        "info": "·",
        "ok": "✓",
        "warn": "!",
        "err": "✗",
        "step": "→",
    }.get(kind, "·")
    print(f"  {prefix} {msg}")


def find_root(start: Path | None = None) -> Path | None:
    """Walk upwards looking for an .aether/ directory."""
    here = (start or Path.cwd()).resolve()
    for p in [here, *here.parents]:
        if (p / AETHER_DIR).is_dir():
            return p
    return None


def require_root() -> Path:
    root = find_root()
    if not root:
        say("No .aether/ found. Run `aether init` first.", "err")
        sys.exit(2)
    return root


def read_config(root: Path) -> dict[str, Any]:
    cfg_path = root / AETHER_DIR / "config.json"
    if not cfg_path.exists():
        say(f"Missing {cfg_path}", "err")
        sys.exit(2)
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def write_config(root: Path, cfg: dict[str, Any]) -> None:
    cfg_path = root / AETHER_DIR / "config.json"
    cfg_path.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def http_get(url: str, timeout: float = 15.0) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": f"aether-cli/{AETHER_VERSION}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


# -----------------------------------------------------------------------------
# Scaffold
# -----------------------------------------------------------------------------


SCAFFOLD_CONFIG: dict[str, Any] = {
    "$schema": "https://497810wsl.github.io/aether/schema/config.v1.json",
    "aether_version": AETHER_VERSION,
    "ontology_version": ONTOLOGY_VERSION,
    "integration": "cursor",
    "installed_fields": [],
    "local_only_fields": [],
    "mirror_mode": "single-user",
    "core_repo": DEFAULT_CORE_REPO,
    "membership": {
        "opted_in": False,
        "since": None,
    },
    "created_at": None,
}


SCAFFOLD_README = """# .aether/ · Your Aether Workspace

This directory is the **local ecosystem** of an Aether-aware project.

- `fields/` — installed concentration fields (installed via `aether fetch`, or hand-authored)
- `collapses/` — every meaningful AI interaction gets recorded here (append-only)
- `nursery/` — candidate species seeds observed by the AI
- `mirror/` — AI's private reflection of the user (sensitive — keep local)
- `config.json` — what this workspace knows about itself
- `MEMBERSHIP.md` — signals this project uses Aether

## Don't commit everything

If you want to share fields but keep mirror/collapses private, add to `.gitignore`:

    .aether/collapses/
    .aether/mirror/
    .aether/nursery/

Keep `.aether/config.json` and `.aether/fields/` versioned.

## Learn more

- <https://github.com/497810wsl/aether>
- docs/USAGE-MODEL.md in the Aether repo

Contact: WeChat `wsl497810`
"""


SCAFFOLD_MEMBERSHIP = """---
aether_member: true
since: {since}
aether_version: {version}
---

# This project uses Aether

Aether is a post-skill architecture for AI knowledge.
It does not replace your tools; it adds a new language layer.

- Core: <https://github.com/497810wsl/aether>
- Contact: WeChat **wsl497810**

Feel free to `aether status` to see the ecosystem's pulse.
"""


SCAFFOLD_MIRROR_ESSENCE = """# User Essence · (AI's reflection)

This file is the AI's mirror of the user — populated gradually from collapses.

At Generation 0 it is empty by design. As collapse events accumulate,
the AI MAY write short observations here. Examples:

    - Preferred verbosity: low
    - Accepts strong critique: yes
    - Primary language: 中文
    - Typical task domains: code review, architecture

The user MAY edit or delete anything here at any time. This is YOUR data.

## Ethical boundary

The AI MUST NOT write here anything the user did not clearly express.
If the AI invents observations, see meta/crisis-handbook.md ("Mirror Intrusion").
"""


SCAFFOLD_CURSOR_RULE = """---
description: "Aether Post-Skill Architecture — highest priority contract"
alwaysApply: true
---

# Aether Contract (this project opted into Aether v{version})

You operate inside an Aether workspace. Before anything else, read:

1. `{aether_dir}/README.md`
2. `{aether_dir}/config.json`
3. Any `.field.md` files inside `{aether_dir}/fields/`

## Language rules (MANDATORY)

This project speaks Aether. Do NOT use these Gen-3 phrases in ANY artifact
you write into `{aether_dir}/`:

- "创建 skill" / "调用 skill" / "删除 skill" / "skill 版本升级"

Instead use Aether vocabulary (see translation-layer):

| Gen 3 (forbidden)  | Aether (required)            |
| ------------------ | ---------------------------- |
| skill              | species                      |
| call a skill       | collapse a field             |
| create a skill     | propose a seed in nursery    |
| update a skill     | adjust field concentration   |

## Activation protocol

When the user writes `activate linus-torvalds=0.7, engineering-rigor=0.6`:

1. Read the matching `.field.md` files in `{aether_dir}/fields/`.
2. Let their vectors influence your reply style & discipline.
3. After replying, PROPOSE writing a collapse event:

```
{aether_dir}/collapses/coll-<nanoid>.md
```

Follow the format used in the Aether Core `labs/examples/` collapse samples.

## What you must NOT do

- Do not write `.species.md` files directly (use nursery).
- Do not modify anything under `chronicle/` (append-only).
- Do not invent observations in `mirror/` that the user didn't express.

## Meta-rule

If you think "let me just generate some fake sample data to make it work" —
**stop**. Aether only grows from real collapses. Wait for the real one.

---

Install source: Aether CLI v{version} · MIT
Contact: WeChat wsl497810
"""


def do_init(args: argparse.Namespace) -> int:
    cwd = Path.cwd().resolve()
    target = cwd / AETHER_DIR
    integration = args.integration

    if target.exists() and not args.force:
        say(f"{target} already exists. Use --force to recreate.", "err")
        return 2

    say(f"Initializing Aether workspace in {cwd}", "step")

    for sub in ("fields", "collapses", "nursery", "mirror"):
        (target / sub).mkdir(parents=True, exist_ok=True)

    (target / "README.md").write_text(SCAFFOLD_README, encoding="utf-8")

    cfg = dict(SCAFFOLD_CONFIG)
    cfg["integration"] = integration
    cfg["created_at"] = now_iso()
    write_config(cwd, cfg)

    (target / "MEMBERSHIP.md").write_text(
        SCAFFOLD_MEMBERSHIP.format(since=now_iso(), version=AETHER_VERSION),
        encoding="utf-8",
    )

    (target / "mirror" / "user-essence.md").write_text(
        SCAFFOLD_MIRROR_ESSENCE, encoding="utf-8"
    )

    for sub in ("fields", "collapses", "nursery"):
        keep = target / sub / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")

    if integration == "cursor":
        rules_dir = cwd / CURSOR_RULES_DIR
        rules_dir.mkdir(parents=True, exist_ok=True)
        rule_path = rules_dir / CURSOR_RULE_FILE
        rule_path.write_text(
            SCAFFOLD_CURSOR_RULE.format(
                version=AETHER_VERSION,
                aether_dir=AETHER_DIR,
            ),
            encoding="utf-8",
        )
        say(f"Wrote Cursor rule → {rule_path.relative_to(cwd)}", "ok")
    elif integration == "claude":
        claude_path = cwd / "CLAUDE.md"
        if claude_path.exists() and not args.force:
            say(f"CLAUDE.md exists; appending Aether section...", "warn")
            existing = claude_path.read_text(encoding="utf-8")
            if "Aether Contract" not in existing:
                claude_path.write_text(
                    existing
                    + "\n\n"
                    + SCAFFOLD_CURSOR_RULE.format(
                        version=AETHER_VERSION, aether_dir=AETHER_DIR
                    ),
                    encoding="utf-8",
                )
        else:
            claude_path.write_text(
                SCAFFOLD_CURSOR_RULE.format(
                    version=AETHER_VERSION, aether_dir=AETHER_DIR
                ),
                encoding="utf-8",
            )
        say(f"Wrote → CLAUDE.md", "ok")
    else:
        say("Integration = generic. You must wire the contract yourself.", "info")
        say("See docs/integration/README.md in the Aether Core repo.", "info")

    say(f"Created {target.relative_to(cwd)}/", "ok")

    if args.preset == "starter":
        say("Installing starter preset (3 fields)...", "step")
        fetched = 0
        for fid in STARTER_PRESET_FIELDS:
            fake_args = argparse.Namespace(field_id=fid, source=None, force=True)
            rc = do_fetch(fake_args)
            if rc == 0:
                fetched += 1
        if fetched == len(STARTER_PRESET_FIELDS):
            say(f"Starter preset installed: {', '.join(STARTER_PRESET_FIELDS)}", "ok")
        else:
            say(f"{fetched}/{len(STARTER_PRESET_FIELDS)} starter fields installed (check network)", "warn")
        say("Try it:", "step")
        say("  aether demo        # see what this does in 30 seconds", "info")
        say("  aether status      # see your ecosystem", "info")
    elif args.preset == "minimal":
        say("Minimal init. No fields installed.", "info")
        say("Next: aether fetch <field-id>  (or re-run with --preset starter)", "info")
    else:
        say("Next steps:", "step")
        say("  1. aether demo                    # see what Aether does", "info")
        say("  2. aether fetch linus-torvalds    # install your first field", "info")
        say("  3. In your AI chat: 'activate linus-torvalds=0.7, review this code'", "info")
        say("  4. aether status                  # watch it grow", "info")
    return 0


# -----------------------------------------------------------------------------
# Fetch
# -----------------------------------------------------------------------------


FIELD_LOCATIONS = [
    "kit/fields/{fid}.field.md",
]


def do_fetch(args: argparse.Namespace) -> int:
    root = require_root()
    cfg = read_config(root)
    base = args.source or cfg.get("core_repo", DEFAULT_CORE_REPO)
    fid = args.field_id

    if not re.match(r"^[a-z0-9\-]+$", fid):
        say(f"Invalid field id: {fid!r}. Use kebab-case.", "err")
        return 2

    target_file = root / AETHER_DIR / "fields" / f"{fid}.field.md"
    if target_file.exists() and not args.force:
        say(f"{target_file.relative_to(root)} already exists (use --force)", "warn")
        return 0

    content = None
    matched_path = None
    for template in FIELD_LOCATIONS:
        url = f"{base}/{template.format(fid=fid)}"
        try:
            say(f"Trying {url}", "step")
            content = http_get(url)
            matched_path = template.format(fid=fid)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            say(f"HTTP {e.code}: {e.reason}", "err")
            return 1
        except urllib.error.URLError as e:
            say(f"Network error: {e.reason}", "err")
            return 1

    if not content:
        say(f"Field {fid!r} not found in Core registry.", "err")
        say("Try `aether list --remote` or ask on GitHub Issues.", "info")
        return 1

    target_file.write_text(content, encoding="utf-8")

    entry = {
        "id": fid,
        "version": "1",
        "source": matched_path,
        "installed_at": now_iso(),
    }
    installed: list[dict[str, Any]] = cfg.setdefault("installed_fields", [])
    installed = [e for e in installed if e.get("id") != fid]
    installed.append(entry)
    cfg["installed_fields"] = sorted(installed, key=lambda e: e["id"])
    write_config(root, cfg)

    say(f"Installed field {fid} → {target_file.relative_to(root)}", "ok")
    return 0


# -----------------------------------------------------------------------------
# List
# -----------------------------------------------------------------------------


def do_list(args: argparse.Namespace) -> int:
    root = require_root()
    cfg = read_config(root)
    fields_dir = root / AETHER_DIR / "fields"

    local_files = sorted(p.stem.replace(".field", "") for p in fields_dir.glob("*.field.md"))
    installed = {e["id"]: e for e in cfg.get("installed_fields", [])}

    print()
    print("  Installed fields:")
    print("  -----------------")
    if not local_files:
        print("  (none yet — try `aether fetch linus-torvalds`)")
    else:
        for fid in local_files:
            meta = installed.get(fid)
            if meta:
                print(f"    ✓ {fid}  v{meta.get('version','1')}  ({meta.get('installed_at','?')})")
            else:
                print(f"    · {fid}  (local-only, not in config)")
    print()
    return 0


# -----------------------------------------------------------------------------
# Collapse
# -----------------------------------------------------------------------------


def parse_fields(spec: str) -> list[tuple[str, float]]:
    pairs = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"Expected id=value, got {chunk!r}")
        fid, val = chunk.split("=", 1)
        fid = fid.strip()
        val_f = float(val.strip())
        if not re.match(r"^[a-z0-9\-]+$", fid):
            raise ValueError(f"Invalid field id: {fid!r}")
        pairs.append((fid, val_f))
    return pairs


COLLAPSE_TEMPLATE = """---
collapse_id: {cid}
timestamp: {ts}
active_fields:
{fields_yaml}
input_signature: {summary!r}
output_hash: unknown
user_reaction: {reaction}
notes: recorded via aether CLI
---

# Collapse {cid}

_Input_: {summary}

_Active fields_:
{fields_md}

_Reaction_: {reaction}

---

(Edit this file to add output samples, analysis, or emergence signals.)
"""


def do_collapse(args: argparse.Namespace) -> int:
    root = require_root()
    try:
        pairs = parse_fields(args.fields)
    except ValueError as e:
        say(str(e), "err")
        return 2

    for term in FORBIDDEN_TERMS:
        if term in args.summary:
            say(f"Gen-3 forbidden term in summary: {term!r}", "err")
            say("Use Aether vocabulary. See meta/translation-layer.md", "info")
            return 2

    cid = f"coll-{nanoid()}"
    fields_yaml = "\n".join(
        f"  - field_id: {fid}\n    concentration: {val}" for fid, val in pairs
    )
    fields_md = "\n".join(f"- `{fid}` = {val}" for fid, val in pairs)

    body = COLLAPSE_TEMPLATE.format(
        cid=cid,
        ts=now_iso(),
        fields_yaml=fields_yaml,
        fields_md=fields_md,
        summary=args.summary,
        reaction=args.reaction,
    )

    outfile = root / AETHER_DIR / "collapses" / f"{cid}.md"
    outfile.write_text(body, encoding="utf-8")
    say(f"Recorded → {outfile.relative_to(root)}", "ok")
    return 0


# -----------------------------------------------------------------------------
# Status
# -----------------------------------------------------------------------------


@dataclass
class Stats:
    fields: int = 0
    collapses: int = 0
    seeds: int = 0
    last_collapse: str | None = None


def gather_stats(root: Path) -> Stats:
    base = root / AETHER_DIR
    s = Stats()
    s.fields = len(list((base / "fields").glob("*.field.md")))
    collapses = sorted((base / "collapses").glob("coll-*.md"))
    s.collapses = len(collapses)
    if collapses:
        s.last_collapse = collapses[-1].name
    s.seeds = len(list((base / "nursery").glob("*.seed.md")))
    return s


def do_status(args: argparse.Namespace) -> int:
    root = require_root()
    cfg = read_config(root)
    stats = gather_stats(root)

    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │              Aether · Status                │")
    print("  ├─────────────────────────────────────────────┤")
    print(f"  │  Root:          {root}".ljust(48) + "│")
    print(f"  │  CLI version:   {AETHER_VERSION}".ljust(48) + "│")
    print(f"  │  Ontology:      v{cfg.get('ontology_version', ONTOLOGY_VERSION)}".ljust(48) + "│")
    print(f"  │  Integration:   {cfg.get('integration','?')}".ljust(48) + "│")
    print(f"  │  Installed fields:  {stats.fields}".ljust(48) + "│")
    print(f"  │  Collapses:         {stats.collapses}".ljust(48) + "│")
    print(f"  │  Seeds in nursery:  {stats.seeds}".ljust(48) + "│")
    last = stats.last_collapse or "(none)"
    print(f"  │  Last collapse:     {last}".ljust(48) + "│")
    mem = cfg.get("membership", {})
    status = "yes" if mem.get("opted_in") else "no"
    print(f"  │  Linked to Core:    {status}".ljust(48) + "│")
    print("  └─────────────────────────────────────────────┘")
    print()

    if stats.fields == 0:
        say("No fields installed. Try: aether fetch linus-torvalds", "info")
    if stats.collapses == 0:
        say("No collapses yet. The ecosystem is quiet.", "info")
    elif stats.collapses < 5:
        say("Early days. Keep collapsing — nursery thresholds are at 5, 20, 30.", "info")

    return 0


# -----------------------------------------------------------------------------
# Link
# -----------------------------------------------------------------------------


def do_link(args: argparse.Namespace) -> int:
    root = require_root()
    cfg = read_config(root)
    mem = cfg.setdefault("membership", {})
    if mem.get("opted_in"):
        say("Already linked.", "info")
        return 0
    mem["opted_in"] = True
    mem["since"] = now_iso()
    write_config(root, cfg)
    say("Linked. Your project is now an Aether member.", "ok")
    say("This is local metadata only — no data is sent anywhere.", "info")
    say("If you'd like to appear on the public roster, open a PR adding your", "info")
    say("project name to docs/adopters.md in the Aether Core repo.", "info")
    return 0


# -----------------------------------------------------------------------------
# Doctor
# -----------------------------------------------------------------------------


def do_doctor(args: argparse.Namespace) -> int:
    root = find_root()
    issues: list[str] = []

    if not root:
        print()
        say("No .aether/ workspace found in current path.", "err")
        say("Run `aether init` to create one.", "info")
        return 2

    cfg_path = root / AETHER_DIR / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        issues.append(f"config.json is not valid JSON: {e}")
        cfg = {}

    if cfg.get("ontology_version") != ONTOLOGY_VERSION:
        issues.append(
            f"Ontology version mismatch: config={cfg.get('ontology_version')}, CLI={ONTOLOGY_VERSION}"
        )

    fields_dir = root / AETHER_DIR / "fields"
    for field_file in fields_dir.glob("*.field.md"):
        text = field_file.read_text(encoding="utf-8")
        for term in FORBIDDEN_TERMS:
            if term in text:
                issues.append(f"Gen-3 term {term!r} in {field_file.name}")

    print()
    if not issues:
        say("All checks passed.", "ok")
        return 0
    say("Found issues:", "warn")
    for i, issue in enumerate(issues, 1):
        print(f"    {i}. {issue}")
    return 1


# -----------------------------------------------------------------------------
# Demo
# -----------------------------------------------------------------------------


def _try_read_local_showcase() -> dict | None:
    """Try to find showcase.json next to the script (in the kit layout)."""
    script_dir = Path(__file__).resolve().parent.parent
    candidate = script_dir / "kit" / "demo" / "showcase.json"
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return None


def _fetch_remote_showcase(base_url: str) -> dict | None:
    try:
        raw = http_get(f"{base_url}/kit/demo/showcase.json")
        return json.loads(raw)
    except Exception:
        return None


def _wrap(text: str, width: int = 72, indent: str = "  ") -> str:
    out_lines: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line:
            out_lines.append("")
            continue
        words = raw_line.split(" ")
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > width:
                out_lines.append(line.rstrip())
                line = w + " "
            else:
                line += w + " "
        if line.strip():
            out_lines.append(line.rstrip())
    return "\n".join(indent + ln if ln else "" for ln in out_lines)


def _print_divider(title: str = "", char: str = "─", width: int = 76) -> None:
    if title:
        padded = f" {title} "
        side = (width - len(padded)) // 2
        print(char * side + padded + char * (width - side - len(padded)))
    else:
        print(char * width)


def _print_scenario(sc: dict, idx: int, total: int) -> None:
    _print_divider(f"Scenario {idx}/{total}: {sc['title']}", char="═")
    print()
    print("  Input:")
    print(_wrap(sc.get("user_input", ""), indent="    "))
    print()
    print("  User asks: " + sc.get("user_request", ""))
    print()

    wo = sc["without_aether"]
    print(f"  [{wo['label']}]")
    _print_divider(char="·")
    print(_wrap(wo["response"]))
    print()
    print("  Problems with this output:")
    for issue in wo.get("issues", []):
        print(f"    - {issue}")
    print()

    wi = sc["with_aether"]
    print(f"  [{wi['label']}]")
    _print_divider(char="·")
    print(_wrap(wi["response"]))
    print()
    print("  What the fields changed:")
    for delta in wi.get("what_changed", []):
        print(f"    + {delta}")
    print()


def do_demo(args: argparse.Namespace) -> int:
    showcase = _try_read_local_showcase()
    if not showcase:
        root = find_root()
        base_url = DEFAULT_CORE_REPO
        if root:
            cfg = read_config(root)
            base_url = cfg.get("core_repo", DEFAULT_CORE_REPO)
        say("Fetching showcase from Core...", "step")
        showcase = _fetch_remote_showcase(base_url)
    if not showcase:
        say("Could not load showcase. Check your network or clone Aether Core locally.", "err")
        return 1

    print()
    _print_divider("Aether · 30-Second Demo", char="═")
    print()
    print("  This is a PRE-RECORDED demonstration showing what happens")
    print("  when Aether fields are active during an AI conversation.")
    print()
    print("  These outputs were observed in real Aether workspaces.")
    print("  Running `aether init` + `aether fetch <field>` in your own")
    print("  Cursor/Claude setup will reproduce this effect on YOUR questions.")
    print()

    scenarios = showcase.get("scenarios", [])
    total = len(scenarios)
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        total = len(scenarios)
        if not scenarios:
            say(f"No scenario with id={args.scenario!r}", "err")
            say(f"Available: {', '.join(s['id'] for s in showcase.get('scenarios', []))}", "info")
            return 2

    for i, sc in enumerate(scenarios, 1):
        _print_scenario(sc, i, total)

    _print_divider("Next step", char="═")
    print()
    print("  Want this effect in your own Cursor/Claude?")
    print()
    print("    aether init --preset starter")
    print("    # (installs linus-torvalds + engineering-rigor + jony-ive)")
    print()
    print("    Then in Cursor chat:")
    print("      'activate linus-torvalds=0.8, engineering-rigor=0.9,")
    print("       now review this function: ...'")
    print()
    print("  Full guide: docs/integration/cursor.md")
    print("  Contact:    WeChat wsl497810")
    print()
    return 0


# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------


def do_version(args: argparse.Namespace) -> int:
    print(f"aether {AETHER_VERSION} · ontology v{ONTOLOGY_VERSION}")
    print(f"Core: {DEFAULT_CORE_REPO}")
    print("License: MIT · Contact: WeChat wsl497810")
    return 0


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aether",
        description="Aether · Post-Skill Architecture CLI",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize .aether/ in current directory")
    p_init.add_argument(
        "--integration",
        choices=["cursor", "claude", "generic"],
        default="cursor",
        help="Which AI environment to wire (default: cursor)",
    )
    p_init.add_argument(
        "--preset",
        choices=["starter", "minimal", "none"],
        default="starter",
        help="starter = install 3 common fields (default); minimal = skip; none = show next-step hints",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite existing files")
    p_init.set_defaults(func=do_init)

    p_fetch = sub.add_parser("fetch", help="Fetch a field from Core")
    p_fetch.add_argument("field_id")
    p_fetch.add_argument("--source", help="Override Core raw URL base")
    p_fetch.add_argument("--force", action="store_true")
    p_fetch.set_defaults(func=do_fetch)

    p_list = sub.add_parser("list", help="List installed fields")
    p_list.add_argument(
        "--type", choices=["style", "discipline", "temperament", "all"], default="all"
    )
    p_list.set_defaults(func=do_list)

    p_col = sub.add_parser("collapse", help="Record a collapse event")
    p_col.add_argument("summary")
    p_col.add_argument("--fields", required=True, help="e.g. 'linus=0.8,rigor=0.6'")
    p_col.add_argument(
        "--reaction",
        choices=["positive", "negative", "neutral", "unknown"],
        default="unknown",
    )
    p_col.set_defaults(func=do_collapse)

    p_stat = sub.add_parser("status", help="Show ecosystem status")
    p_stat.set_defaults(func=do_status)

    p_link = sub.add_parser("link", help="Mark this project as an Aether member")
    p_link.set_defaults(func=do_link)

    p_doc = sub.add_parser("doctor", help="Diagnose the workspace")
    p_doc.set_defaults(func=do_doctor)

    p_demo = sub.add_parser(
        "demo",
        help="Show a 30-second demo comparing AI output with vs. without Aether",
    )
    p_demo.add_argument(
        "--scenario",
        help="Show only one scenario (code-review | debugging | writing)",
    )
    p_demo.set_defaults(func=do_demo)

    p_ver = sub.add_parser("version", help="Show version")
    p_ver.set_defaults(func=do_version)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        say("Interrupted.", "warn")
        return 130
    except Exception as e:  # noqa: BLE001
        say(f"Unhandled error: {e!r}", "err")
        return 1


if __name__ == "__main__":
    sys.exit(main())
