#!/usr/bin/env python3
"""
aether_paths.py — Single source of truth for Aether path resolution.

Day 11 (post-coll-0082) · fixes the D-layer half of the Day 9 read/write
asymmetry.

## Why this module exists

Before Day 11, at least three places independently decided "where is the
aether data dir?":

  1. aether_events.resolve_overlay_dir(payload)   — hook-time, payload-aware
  2. aether_handshake.resolve_workspace_root()    — handshake, its own env var
  3. aether_tasks/daily/doctor/indexer/guardian/  — hard-coded WORKSPACE_ROOT
     summarizer/autopilot/query

The third group made `aether tasks add P0 "..."` always write to the
CENTRAL repo's .aether/, even when the user was in a guest project with
their own overlay. Day 10's `aether project init` was therefore only
cosmetically federated: hooks wrote per-project, but user-facing CLIs
still dumped into central.

This module makes `cwd`-aware overlay resolution a shared primitive so
any CLI can opt in.

## Resolution order for `resolve_active_overlay()`

Designed specifically for CLI commands invoked by the user (via the
global `aether` wrapper or direct `python aether_X.py`). Hook handlers
should keep using `aether_events.resolve_overlay_dir(payload)`.

    1. explicit_path argument              (e.g. --path flag)
    2. AETHER_DATA_DIR env var             (test harness / power user)
    3. walk upward from cwd for `.aether/` (git-style discovery)
    4. fall back to central's .aether/     (safe last resort · avoids
                                            spawning stray dirs in C:\\)

The upward walk stops at filesystem root. Both the project root's
`.aether/` and any parent containing one is valid — nearest wins.

## Contract

* Returned paths may not exist yet. Callers that INTEND to write must
  `mkdir(parents=True, exist_ok=True)` themselves.
* `explicit_path` is treated literally (not walked). If user passes
  `--path /nonexistent`, callers get `/nonexistent/.aether`. Callers
  should validate if they care.

## Non-goals

* This module does NOT decide WHICH files to read/write — that's each
  CLI's job. It only answers "where is the overlay root I should use".
* It does NOT replace payload-based resolution for hooks. Hooks always
  have authoritative workspace_roots from Cursor.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── constants ────────────────────────────────────────────────────────

_THIS = Path(__file__).resolve()
_BIN_DIR = _THIS.parent                         # aether/bin/
_AETHER_DIR = _BIN_DIR.parent                   # aether/
CENTRAL_ROOT = _AETHER_DIR.parent               # the central skills repo

OVERLAY_DIRNAME = ".aether"
CENTRAL_OVERLAY = CENTRAL_ROOT / OVERLAY_DIRNAME

CORE_HOME = Path.home() / ".aether-core"
CORE_SUBDIR = CORE_HOME / "core"

ENV_DATA_DIR = "AETHER_DATA_DIR"                # preferred (matches events.py)
ENV_WORKSPACE = "AETHER_WORKSPACE"              # accepted (handshake compat)


# ─── core ─────────────────────────────────────────────────────────────

def resolve_core_dir() -> Path:
    """Owner-scope core directory: `~/.aether-core/core/`.

    May not exist yet (run `aether federate init-core --apply` to create).
    """
    return CORE_SUBDIR


# ─── overlay · CLI-facing (walks up from cwd) ────────────────────────

def _find_overlay_upward(start: Path) -> Optional[Path]:
    """Walk from `start` to filesystem root looking for a `.aether/` dir.

    Returns the FIRST `.aether/` found (nearest to start), or None.
    """
    try:
        here = start.resolve()
    except OSError:
        return None
    seen: set[Path] = set()
    cursor = here
    while True:
        if cursor in seen:
            return None
        seen.add(cursor)
        candidate = cursor / OVERLAY_DIRNAME
        if candidate.is_dir():
            return candidate
        parent = cursor.parent
        if parent == cursor:                     # hit filesystem root
            return None
        cursor = parent


def _env_override() -> Optional[Path]:
    for name in (ENV_DATA_DIR, ENV_WORKSPACE):
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            p = Path(raw).expanduser().resolve()
        except Exception:
            continue
        # AETHER_WORKSPACE is a PROJECT ROOT · append .aether/
        if name == ENV_WORKSPACE and not p.name == OVERLAY_DIRNAME:
            p = p / OVERLAY_DIRNAME
        return p
    return None


def resolve_active_overlay(
    explicit_path: Optional[str | Path] = None,
    cwd: Optional[str | Path] = None,
) -> tuple[Path, str]:
    """Resolve the overlay a CLI command should act on.

    Returns (overlay_dir, source_label) where source_label is one of:
      "explicit"  — explicit_path argument was used
      "env"       — AETHER_DATA_DIR / AETHER_WORKSPACE env var
      "discovered"— found `.aether/` by walking up from cwd
      "central"   — nothing found, using central's .aether/ (fallback)

    `explicit_path` is treated as a PROJECT ROOT (we append .aether/
    automatically) unless it already ends in `.aether`. This matches how
    `aether_project.py --path` is documented.
    """
    if explicit_path is not None:
        p = Path(explicit_path).expanduser()
        try:
            p = p.resolve()
        except Exception:
            pass
        if p.name != OVERLAY_DIRNAME:
            p = p / OVERLAY_DIRNAME
        return p, "explicit"

    env_p = _env_override()
    if env_p is not None:
        return env_p, "env"

    cwd_path = Path(cwd) if cwd else Path.cwd()
    found = _find_overlay_upward(cwd_path)
    if found is not None:
        return found, "discovered"

    return CENTRAL_OVERLAY, "central"


# ─── CLI activation helper · Day 13 · PATH-RESOLUTION-SPEC §2.4 ──────
#
# Before Day 13, aether_tasks / aether_daily / aether_doctor each hand-wrote
# their own `_activate_overlay()` function (~15 lines each). Day 13 adds 5
# more CLIs that would need the same code (indexer / guardian / autopilot /
# summarizer / query). Single function here = one behavior to maintain.
#
# Usage from a CLI:
#
#     args = ap.parse_args()
#     overlay, source = activate_overlay_for_cli(args, announce=not args.json)
#     # ... use overlay / source from here on

def activate_overlay_for_cli(
    args,
    announce: bool = True,
    stream=None,
) -> tuple[Path, str]:
    """Resolve overlay from `args.path` (argparse Namespace) + print banner.

    `args` is expected to be an argparse.Namespace with an optional `.path`
    attribute (the `--path` flag value · may be None). We also look for
    `.json` / `.quiet` attributes to auto-suppress the banner when stdout
    is being consumed programmatically.

    Returns (overlay_dir, source_label) · same as resolve_active_overlay.
    Prints one-line scope banner to stderr (unless suppressed).
    """
    explicit = None
    try:
        explicit = getattr(args, "path", None)
    except Exception:
        explicit = None

    overlay, source = resolve_active_overlay(explicit_path=explicit)

    if not announce:
        return overlay, source

    # Auto-suppress when --json or --quiet is in play
    try:
        if getattr(args, "json", False) or getattr(args, "as_json", False):
            return overlay, source
        if getattr(args, "quiet", False):
            return overlay, source
    except Exception:
        pass

    out = stream if stream is not None else sys.stderr
    name = overlay.parent.name or str(overlay.parent)
    try:
        if source == "central":
            print(
                "  · scope: central  (no .aether/ found walking up from cwd)",
                file=out,
            )
        elif source == "discovered":
            print(f"  · scope: {name}", file=out)
        elif source == "env":
            print(f"  · scope: {name}  (via env)", file=out)
        elif source == "explicit":
            print(f"  · scope: {name}  (via --path)", file=out)
    except Exception:
        pass

    return overlay, source


def add_path_arg(parser) -> None:
    """Attach the canonical `--path` flag to an argparse parser/subparser.

    Single source for the flag's help text so every CLI uses identical
    wording. Usage:

        ap = argparse.ArgumentParser(...)
        add_path_arg(ap)

    For subparsers · call `add_path_arg(subparser)` on each.
    """
    try:
        parser.add_argument(
            "--path",
            help="project root whose .aether/ to use (default: walk up from cwd)",
        )
    except Exception:
        # argparse raises if --path already exists on this parser · tolerate
        pass


def resolve_overlay_dir(payload: Optional[dict] = None) -> Path:
    """Hook/payload-oriented resolution · kept in sync with events.py.

    This is the path to use when you have a Cursor hook payload; it does
    NOT walk cwd (hooks may run from any cwd). CLI code should call
    `resolve_active_overlay()` instead.
    """
    env_p = _env_override()
    if env_p is not None:
        return env_p

    if isinstance(payload, dict):
        roots = payload.get("workspace_roots") or []
        if isinstance(roots, list) and roots:
            try:
                first = str(roots[0]).strip()
                # Cursor sometimes emits /c:/foo · normalize to c:/foo
                if len(first) >= 4 and first[0] == "/" and first[2] == ":":
                    first = first[1] + ":" + first[3:]
                rp = Path(first).expanduser().resolve()
                if rp.exists() and rp.is_dir():
                    return rp / OVERLAY_DIRNAME
            except Exception:
                pass

    return CENTRAL_OVERLAY


# ─── JSON with BOM tolerance ─────────────────────────────────────────

def read_json_tolerant(
    path: Path,
    default=None,
    on_error="default",
):
    """Read a JSON file tolerating UTF-8 BOM.

    Windows Notepad / some editors save JSON with a BOM which makes
    plain utf-8 decoding choke on the first char. This helper accepts
    both. It also returns `default` on missing / unreadable / malformed
    files, so call sites don't need three layers of try/except.

    on_error:
      "default" (default) — return `default` on JSONDecodeError / OSError
      "raise"             — re-raise
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return default
    except OSError:
        if on_error == "raise":
            raise
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if on_error == "raise":
            raise
        return default


# ─── subcommand discovery (wrapper help generation) ──────────────────

def iter_subcommand_scripts() -> list[str]:
    """Return sorted list of aether_*.py subcommand names (without prefix).

    Used by aether_install.py to generate wrapper help dynamically
    instead of hand-maintaining a short list.

    Excludes `aether_paths` (internal infra), `aether_hook` (Cursor-
    invoked shim, never a user command), and the standalone `aether.py`
    kit CLI (not routed through the wrapper).
    """
    excluded = {"aether_paths", "aether_hook"}
    names: list[str] = []
    for p in _BIN_DIR.glob("aether_*.py"):
        stem = p.stem                            # aether_tasks
        if stem in excluded:
            continue
        names.append(stem[len("aether_"):])      # "tasks"
    return sorted(names)


# Curated list of the commands most worth surfacing in help output.
# Keep short — full list via iter_subcommand_scripts().
COMMON_SUBCOMMANDS = (
    "daily",
    "tasks",
    "project",
    "federate",
    "doctor",
    "query",
    "selfcheck",
    "install",
)


# ─── ANSI terminal helpers (Day 12 · coll-0084 · Tier-2 consolidation) ─
#
# Before Day 12 at least six CLIs (project / federate / install / doctor
# / daily / selfcheck) each maintained their own copy of these constants
# plus a helper `_c()` / `c()`. Drift was inevitable (e.g. doctor had
# nested helpers that mirrored the module-level ones). This section is
# the single source · callers do `from aether_paths import c, BOLD, ...`.

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
MAGENTA = "\033[35m"
CYAN   = "\033[36m"
GRAY   = "\033[90m"


def c(code: str, text: str, color: bool = True) -> str:
    """Wrap `text` in ANSI `code` when `color` is True · plain otherwise.

    Signature kept identical to every existing `_c()` in the codebase so
    callers can migrate with `from aether_paths import c as _c`.
    """
    return f"{code}{text}{RESET}" if color else text


def want_color(stream=None, force_no_color: bool = False) -> bool:
    """Decide whether ANSI color should be emitted.

    Order of resolution:
      1. `force_no_color=True` (from `--no-color` flag) → False
      2. NO_COLOR env var set → False  (honors http://no-color.org)
      3. stream not a TTY      → False  (piped output)
      4. otherwise             → True

    `stream` defaults to sys.stdout.
    """
    if force_no_color:
        return False
    if os.environ.get("NO_COLOR", ""):
        return False
    s = stream if stream is not None else sys.stdout
    try:
        return bool(s.isatty())
    except Exception:
        return False


# ─── Time format helpers (Day 12 · Tier-2 consolidation) ──────────────
#
# Before Day 12, seven files had their own `now_iso` / `_now_iso` /
# `_now_iso_utc` with subtle differences (microsecond vs millisecond vs
# no subsecond · Z suffix vs +00:00 · multiple datetime.now() calls that
# could race across second boundaries). Normalize here.

def now_iso(millis: bool = False) -> str:
    """UTC ISO 8601 timestamp · Python default precision (microseconds).

    This matches the historical default used by `datetime.now(...).isoformat()`.
    For event schemas that want millisecond precision and a Z suffix,
    use `now_iso_millis()` instead.
    """
    if millis:
        return now_iso_millis()
    return datetime.now(timezone.utc).isoformat()


def now_iso_millis() -> str:
    """UTC ISO 8601 · millisecond precision · Z suffix.

    Single `datetime.now()` call · avoids the Day-1 `events.py` bug where
    two separate `now()` calls could disagree across second boundaries.
    """
    t = datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def now_iso_filename() -> str:
    """Filename-safe timestamp · `YYYYMMDDTHHMMSSZ` · no punctuation.

    For drafts / snapshots where Windows filesystems dislike colons.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


__all__ = [
    "CENTRAL_ROOT",
    "CENTRAL_OVERLAY",
    "OVERLAY_DIRNAME",
    "CORE_HOME",
    "CORE_SUBDIR",
    "ENV_DATA_DIR",
    "ENV_WORKSPACE",
    "resolve_core_dir",
    "resolve_overlay_dir",
    "resolve_active_overlay",
    "activate_overlay_for_cli",
    "add_path_arg",
    "read_json_tolerant",
    "iter_subcommand_scripts",
    "COMMON_SUBCOMMANDS",
    # terminal
    "RESET", "BOLD", "DIM",
    "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "GRAY",
    "c", "want_color",
    # time
    "now_iso", "now_iso_millis", "now_iso_filename",
]
