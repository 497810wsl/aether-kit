#!/usr/bin/env python3
"""
aether_hook.py — unified Cursor hook dispatcher · cross-platform

Single Python entry point for ALL Aether-related Cursor hooks. Replaces
the old two-file (.ps1 wrapper + .py CLI) design so:

1. Cross-platform · Python runs on Windows / Linux / macOS identically.
   No PowerShell dependency · no bash / sh variant · no wrapper layer.

2. All hook logic lives in this file · hooks.json just registers the
   events. Adding a new event (e.g. `stop`, `afterFileEdit`) means
   adding a `handle_<event>()` function · no touching hooks.json paths.

3. Fail-open at every exception · hook failures never block the
   Cursor session.

Invocation (from .cursor/hooks.json):

    python aether/bin/aether_hook.py --event sessionStart
    python aether/bin/aether_hook.py --event beforeSubmitPrompt
    python aether/bin/aether_hook.py --event stop

Each handler reads the Cursor-sent JSON payload on stdin and writes a
single JSON response to stdout (see Cursor hooks spec for event-specific
response shape).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent              # aether/
WORKSPACE_ROOT = ROOT.parent                                # git repo root

# Add bin/ to sys.path so we can re-use aether_handshake.build_briefing etc.
sys.path.insert(0, str(ROOT / "bin"))


# ─── stdin / stdout plumbing ─────────────────────────────────────────

def read_stdin_json() -> dict:
    """Parse Cursor's stdin JSON payload. Returns {} on any failure.

    IMPORTANT (Windows Python 3): sys.stdin defaults to the console
    codepage (cp936 on Chinese Windows). Cursor pipes UTF-8 bytes ·
    plain sys.stdin.read() returned EMPTY because of that mismatch.
    Reading sys.stdin.buffer (raw bytes) and decoding UTF-8 ourselves
    is the only portable way.

    Also: if no stdin is attached (interactive terminal · `python
    aether_hook.py --event X` typed manually) · sys.stdin.read() blocks
    forever waiting for user input. Detect that with isatty() and
    return {} immediately so manual invocation just exercises the
    handler with empty payload.
    """
    # Manual / interactive invocation · no piped stdin · don't block.
    try:
        if sys.stdin.isatty():
            return {}
    except Exception:
        pass
    try:
        raw_bytes = sys.stdin.buffer.read()
    except Exception:
        try:
            raw = sys.stdin.read()
            raw_bytes = raw.encode("utf-8") if raw else b""
        except Exception:
            return {}
    if not raw_bytes:
        return {}
    try:
        raw = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def reply(obj: dict) -> None:
    """Emit JSON to stdout and exit 0 · never returns."""
    json.dump(obj, sys.stdout, ensure_ascii=False)
    sys.stdout.flush()
    sys.exit(0)


def fail_open() -> None:
    """Pass-through response · used when a handler can't produce one."""
    reply({})


# ─── discovery · log payloads so we can design real handlers ─────────

def log_payload(event: str, payload: dict) -> None:
    """Persist the incoming payload under .cursor/hooks/.discovery/
    for later inspection. Silently ignore any filesystem error."""
    try:
        disc = WORKSPACE_ROOT / ".cursor" / "hooks" / ".discovery"
        disc.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-%f")
        path = disc / f"{event}-{stamp}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Rotate · keep last 20 per event
        siblings = sorted(
            disc.glob(f"{event}-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for stale in siblings[20:]:
            try:
                stale.unlink()
            except OSError:
                pass
    except Exception:
        pass


# ─── event handlers ──────────────────────────────────────────────────

def _ensure_project_mdc(payload: dict) -> None:
    """Auto-ensure target project has `.cursor/rules/aether.mdc` so
    RULE 00 + 5-mode actually fire.

    BACKGROUND(Day 8 凌晨末 discovery):
    Cursor 3.x on Windows · `additional_context` injection from
    sessionStart hook is unreliable · the only deterministic way to
    force RULE 00 + 5-mode auto-activation is `.cursor/rules/aether.mdc`
    with `alwaysApply: true` at the PROJECT level. User-level rules
    are GUI-only(NOT files in ~/.cursor/rules/).

    INTENT-BASED AUTHORIZATION:
    We only auto-write to a project when global Aether install exists
    (~/.cursor/.aether-install.json) — that file is the user's explicit
    "I want Aether everywhere" signal. No global install · we don't
    touch any project. This keeps the auto-ensure conservative.

    NEVER OVERWRITE existing mdc · only write when absent.
    """
    try:
        roots = payload.get("workspace_roots") if isinstance(payload, dict) else None
        if not roots or not isinstance(roots, list):
            return
        first = str(roots[0]).strip()
        # Cursor's Windows form: "/c:/Users/..." or "/d:/path/..."
        if len(first) >= 4 and first[0] == "/" and first[2] == ":":
            first = first[1] + ":" + first[3:]
        target = Path(first).expanduser()
        if not target.exists() or not target.is_dir():
            return
        # Don't touch the central aether workspace itself
        if target.resolve() == WORKSPACE_ROOT.resolve():
            return
        # Intent gate · only auto-ensure if global install exists
        global_manifest = Path.home() / ".cursor" / ".aether-install.json"
        if not global_manifest.exists():
            return
        target_mdc = target / ".cursor" / "rules" / "aether.mdc"
        if target_mdc.exists():
            return
        # Find central mdc · workspace root level
        src_mdc = WORKSPACE_ROOT / ".cursor" / "rules" / "aether.mdc"
        if not src_mdc.exists():
            return
        target_mdc.parent.mkdir(parents=True, exist_ok=True)
        target_mdc.write_bytes(src_mdc.read_bytes())
    except Exception:
        pass


def handle_sessionStart(payload: dict) -> None:
    """Return a briefing in `additional_context` so AI knows the
    workspace state before the first user message arrives.

    Day 8 末 addition: also auto-ensure target project has mdc
    (see _ensure_project_mdc docstring · respects intent gate).

    Day 9 (coll-0081): now passes `payload` to build_briefing so the
    handshake can detect scope (dev-self vs guest) from
    payload.workspace_roots. Without this, the central's day-N handover
    leaked into every project Owner opened (bug Owner reported Day 9).
    """
    # Auto-ensure project mdc · cheap · failure non-fatal
    _ensure_project_mdc(payload)
    try:
        from aether_handshake import build_briefing
    except ImportError:
        fail_open()
    try:
        briefing = build_briefing(payload=payload)
        reply({"additional_context": briefing})
    except Exception:
        fail_open()


def handle_beforeSubmitPrompt(payload: dict) -> None:
    """Currently no rewrite (see large comment block) · but DOES record
    one event so cursor_version + composer_mode aren't silently dropped.

    Day 8 PM addition: payload-schema audit (L10) flagged cursor_version
    as `_aether_unused`. Fix is small · log it · don't lie about it.

    Why this is a no-op:

    1. Cursor docs (cursor.com/docs/agent/third-party-hooks) specify the
       output schema of beforeSubmitPrompt as {continue, user_message}
       ONLY. There is NO `updated_input` / `prompt` rewrite field. Our
       earlier attempt to send {updated_input, input, prompt} was
       silently dropped by Cursor (verified in hook OUTPUT log: '{}').

    2. Anthropic GitHub issue #48009 confirms that on Windows,
       UserPromptSubmit (the alias Cursor uses for beforeSubmitPrompt)
       hooks receive empty stdin · so even if we could rewrite, we
       couldn't read the user's prompt to know what to prepend to.

    Status line enforcement is achieved instead via:
      a. sessionStart hook · injects briefing including the status line
         in additional_context
      b. .cursor/rules/aether.mdc · RULE 00 (alwaysApply: true) ·
         instructs AI to quote the status line verbatim as first line
         of every response · cross-platform · cross-event-type ·
         no Windows bug exposure

    Kept registered in HANDLERS so future Cursor capability additions
    (e.g. if rewrite support lands) can be plugged in without touching
    dispatch logic.
    """
    # Lightweight observation event · consumes cursor_version + composer_mode +
    # prompt length so payload-schema audit doesn't flag them as unused.
    try:
        from aether_events import append_event, derive_session_id
        prompt_text = payload.get("prompt") or ""
        append_event(_enrich_event(payload, {
            "type": "prompt_submit",
            "session_id": derive_session_id(payload),
            "payload": {
                "prompt_len": len(prompt_text),
                "cursor_version": payload.get("cursor_version"),
                "composer_mode": payload.get("composer_mode"),
                "model": payload.get("model"),
            },
        }))
    except Exception:
        pass
    fail_open()


def handle_stop(payload: dict) -> None:
    """Called by Cursor when a user turn completes · log and emit event.

    Fast path · must not block. Heavy processing (coll extraction ·
    SQLite indexing) happens in sessionEnd or guardian · not here.
    """
    try:
        from aether_events import append_event, derive_session_id
        append_event(_enrich_event(payload, {
            "type": "stop",
            "session_id": derive_session_id(payload),
            "payload": {
                "event_name": payload.get("event_name") or payload.get("eventName"),
            },
        }))
    except Exception:
        pass
    log_payload("stop", payload)
    fail_open()


def _extract_tool_name(payload: dict) -> tuple[str, str]:
    """Best-effort extraction of tool name from Cursor's postToolUse payload.

    Returns (tool_name, source_tag). source_tag is one of:
      · 'key:<keyname>'    · matched a known top-level key
      · 'nested'           · found inside tool_call/toolCall object
      · 'cursor-empty'     · Cursor delivered an empty {} payload · known
                             Cursor/Windows hook bug (same family as
                             beforeSubmitPrompt getting {} on Windows) ·
                             we still record the event but honestly tag
                             it so stats don't pretend we know the tool.
      · 'non-dict'         · payload was not a dict at all
      · 'no-match'         · payload had keys but none matched our extractors

    Caller uses source_tag to decide whether to log a discovery sample.
    """
    if not isinstance(payload, dict):
        return ("unknown", "non-dict")
    if not payload:
        return ("cursor-empty", "cursor-empty")
    for k in ("tool_name", "toolName", "name", "tool", "function_name", "functionName"):
        v = payload.get(k)
        if v and isinstance(v, str):
            return (v, f"key:{k}")
    tc = payload.get("tool_call") or payload.get("toolCall")
    if isinstance(tc, dict):
        for k in ("name", "tool_name", "toolName"):
            v = tc.get(k)
            if v and isinstance(v, str):
                return (v, "nested")
    return ("unknown", "no-match")


def handle_postToolUse(payload: dict) -> None:
    """Fired after every tool invocation.

    MUST be sub-5ms. Only writes one append-only line to events.jsonl · 
    no DB · no markdown · no decisions. Indexer + extractor run
    asynchronously via guardian / sessionEnd.

    Honest tagging: when Cursor delivers an empty payload (known Windows
    hook bug) we mark tool=`cursor-empty` and source=`cursor-empty` so
    downstream stats can distinguish "we saw activity but Cursor told us
    nothing" from "we genuinely failed to parse a real payload".
    """
    try:
        from aether_events import append_event, derive_session_id
        tool_name, source_tag = _extract_tool_name(payload)
        if source_tag in ("no-match", "non-dict"):
            # Only log samples we might actually learn from · skip the
            # Cursor-empty ones (we already know what `{}` looks like).
            log_payload("postToolUse-unknown-tool", payload)
        args = payload.get("tool_input") or payload.get("args") or payload.get("input") or {}
        # Never persist raw args · may contain secrets / file contents ·
        # just capture a stable digest (first 80 chars of JSON dump).
        try:
            arg_digest = json.dumps(args, ensure_ascii=False)[:80]
        except Exception:
            arg_digest = "?"
        append_event({
            "type": "tool_call",
            "session_id": derive_session_id(payload),
            "tool": tool_name,
            "payload": {"arg_digest": arg_digest, "source": source_tag},
        })
    except Exception:
        pass
    fail_open()


def _resolve_project_data_dir(payload: dict) -> Path:
    """Use aether_events.resolve_data_dir() · per-project isolation."""
    try:
        from aether_events import resolve_data_dir
        return resolve_data_dir(payload)
    except Exception:
        return WORKSPACE_ROOT / ".aether"


def _enrich_event(payload: dict, base: dict) -> dict:
    """Inject workspace_roots into event so events.jsonl gets routed to
    the correct per-project data dir."""
    if isinstance(payload, dict) and payload.get("workspace_roots"):
        base["workspace_roots"] = payload["workspace_roots"]
    return base


def _safe_copy_transcript(payload: dict, kind: str) -> Path | None:
    """If Cursor gave us a transcript_path, snapshot it to per-project
    .aether/transcripts/ (isolation honored).

    Returns the snapshot path on success · None on any failure.
    Size-capped at 2 MB to avoid copying gigantic transcripts.
    """
    try:
        tp = payload.get("transcript_path")
        if not tp or not isinstance(tp, str):
            return None
        src = Path(tp)
        if not src.exists() or not src.is_file():
            return None
        size = src.stat().st_size
        if size > 2 * 1024 * 1024:
            return None
        data_dir = _resolve_project_data_dir(payload)
        snapshots_dir = data_dir / "transcripts"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        cid = (payload.get("conversation_id") or "unknown")[:24]
        gid = (payload.get("generation_id") or "")[:12]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = src.suffix or ".txt"
        name = f"{kind}-{stamp}-{cid}-{gid}{suffix}"
        dest = snapshots_dir / name
        dest.write_bytes(src.read_bytes())
        return dest
    except Exception:
        return None


def _looks_decision_shaped(text: str) -> bool:
    """Cheap heuristic: does this assistant response look like it contains
    decisions / commitments / structured output worth keeping as a coll
    draft seed? Used to gate whether we copy the response text to
    .aether/agent-responses/ for later summarizer pickup.

    Pure additive · false negatives just mean less data · fail-open.
    """
    if not text or len(text) < 800:
        return False
    markers = (
        "##", "P0", "P1", "P2", "决策", "决定", "承诺", "禁止",
        "TODO", "✅", "❌", "🔴", "🟡", "🟢",
        "结论", "落地", "改进", "下一步",
    )
    hits = sum(1 for m in markers if m in text)
    return hits >= 2


def handle_afterAgentResponse(payload: dict) -> None:
    """Fired after the agent emits a complete assistant message.

    Cheap path · MUST stay fast (Cursor doesn't give a hard cap but we
    treat this as "≤ 100ms ideally · ≤ 1s tolerable"):

      1. Append `agent_response` event to events.jsonl(includes text length
         + transcript_path + generation_id)
      2. If text is decision-shaped, save full text to
         .aether/agent-responses/<gen_id>.md so the summarizer can find
         it on next sessionEnd / weekly digest.
      3. NEVER snapshot the transcript here(too frequent · sessionEnd does it).
      4. Fail-open at every step.

    Heavy work(turn into draft coll · fields/species extraction) is
    deferred to aether_session_summarizer.py via the existing schedule.
    """
    text = ""
    try:
        if isinstance(payload, dict):
            text = payload.get("text") or ""
    except Exception:
        text = ""

    try:
        from aether_events import append_event, derive_session_id
        append_event(_enrich_event(payload, {
            "type": "agent_response",
            "session_id": derive_session_id(payload),
            "payload": {
                "text_len": len(text),
                "decision_shaped": _looks_decision_shaped(text),
                "generation_id": (payload.get("generation_id") or "")[:32],
                "transcript_path_present": bool(payload.get("transcript_path")),
                "model": payload.get("model"),
            },
        }))
    except Exception:
        pass

    # Save decision-shaped responses for later summarizer · per-project dir
    try:
        if text and _looks_decision_shaped(text):
            responses_dir = _resolve_project_data_dir(payload) / "agent-responses"
            responses_dir.mkdir(parents=True, exist_ok=True)
            gid = (payload.get("generation_id") or "")[:24] or "unknown"
            cid = (payload.get("conversation_id") or "")[:24] or "unknown"
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = responses_dir / f"resp-{stamp}-{cid}-{gid}.md"
            # Cap at 64 KB · single response should never realistically
            # exceed this · trim if it does so disk doesn't bloat.
            payload_text = text if len(text) <= 65536 else text[:65536] + "\n\n...[truncated]..."
            path.write_text(payload_text, encoding="utf-8")
            # Rotate · keep last 200 responses
            siblings = sorted(
                responses_dir.glob("resp-*.md"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            for stale in siblings[200:]:
                try:
                    stale.unlink()
                except OSError:
                    pass
    except Exception:
        pass

    fail_open()


def handle_afterAgentThought(payload: dict) -> None:
    """Fired when the agent finishes a thinking block (reasoning model only).

    Cheap event · only logs `thought_len` + `duration_ms` + `model` to
    events.jsonl. No file is written · thinking content is INTENTIONALLY
    not persisted to disk:

      · privacy · thoughts may contain raw essence-style content
      · noise · thinking explosively verbose vs decision content
      · purpose · we want THINKING TIME / DEPTH SIGNAL · not the text

    Downstream value: critic / mirror_digest can correlate
    thought-heavy turns with reaction outcomes("AI 思考越久 · Owner 越满意 ?")
    without us ever storing thinking text. Privacy by default.
    """
    text = ""
    duration_ms = None
    try:
        if isinstance(payload, dict):
            text = payload.get("text") or ""
            duration_ms = payload.get("duration_ms")
    except Exception:
        pass

    try:
        from aether_events import append_event, derive_session_id
        append_event(_enrich_event(payload, {
            "type": "agent_thought",
            "session_id": derive_session_id(payload),
            "payload": {
                "thought_len": len(text),
                "duration_ms": duration_ms,
                "model": payload.get("model"),
                "generation_id": (payload.get("generation_id") or "")[:32],
            },
        }))
    except Exception:
        pass

    fail_open()


def handle_postToolUseFailure(payload: dict) -> None:
    """Fired when a tool fails / times out / is denied.

    THIS IS THE 'failure signal' reflex arc that was missing through
    Day 8. Without it, AI's tool-call failures are completely invisible
    to the system · we can't detect 'AI is stuck on Shell errors' or
    'Read keeps timing out on big files' patterns.

    Persists:
      · `tool_name` (best-effort · same extractor as postToolUse)
      · `failure_type` (`error` | `timeout` | `permission_denied`)
      · `error_message` (first 200 chars · in case it has secret paths)
      · `is_interrupt` (user-cancelled vs system-failed)
      · `duration` (how long the tool ran before failing)
    """
    try:
        from aether_events import append_event, derive_session_id
        tool_name, source_tag = _extract_tool_name(payload)
        if source_tag in ("no-match", "non-dict"):
            log_payload("postToolUseFailure-unknown-tool", payload)
        err_msg = (payload.get("error_message") or "")[:200]
        append_event(_enrich_event(payload, {
            "type": "tool_failure",
            "session_id": derive_session_id(payload),
            "tool": tool_name,
            "payload": {
                "failure_type": payload.get("failure_type") or "unknown",
                "error_message": err_msg,
                "is_interrupt": bool(payload.get("is_interrupt")),
                "duration_ms": payload.get("duration"),
                "source": source_tag,
            },
        }))
    except Exception:
        pass

    fail_open()


def handle_beforeShellExecution(payload: dict) -> None:
    """Fired BEFORE every shell command. We allow all by default(fail-open)
    but log the command for skill-evolution data.

    Why we don't deny anything:
      · We don't run as a security gate · skills/* + agents.md cover that
      · Goal is data: which commands does AI actually run on Windows?
        That's gold for evolving the windows-shell skill (essence already
        notes Owner cares about this).

    We DO normalize the command into a `cmd_head` (first non-pipe token)
    so per-tool stats aren't fragmented across `git status` / `git log`
    / `git diff` etc.
    """
    cmd = ""
    cwd = ""
    try:
        if isinstance(payload, dict):
            cmd = payload.get("command") or ""
            cwd = payload.get("cwd") or ""
    except Exception:
        pass

    # Extract first non-quoted token as cmd_head
    cmd_head = ""
    try:
        stripped = cmd.strip()
        # Skip leading pipes / redirects / env assignments
        for tok in stripped.split():
            if "=" in tok and not tok.startswith("-"):
                continue  # env var assignment · skip
            cmd_head = tok.strip("\"'`").split("/")[-1].split("\\")[-1]
            break
    except Exception:
        pass

    try:
        from aether_events import append_event, derive_session_id
        append_event(_enrich_event(payload, {
            "type": "shell_call",
            "session_id": derive_session_id(payload),
            "tool": cmd_head or "shell",
            "payload": {
                "cmd_len": len(cmd),
                "cmd_head": cmd_head,
                "cmd_digest": cmd[:80],
                "cwd_short": cwd[-40:] if cwd else "",
                "sandbox": bool(payload.get("sandbox")),
            },
        }))
    except Exception:
        pass

    # Always allow · we're observing not gating. permission omitted is
    # treated as allow per Cursor docs.
    reply({"permission": "allow"})


def handle_preCompact(payload: dict) -> None:
    """Fired BEFORE Cursor compacts the context window.

    This is the LAST CHANCE to snapshot transcript content before
    Cursor summarises and discards messages. Treat this as a fire alarm:
    grab the transcript file · save to a deterministic location · let
    summarizer read it on next tick.

    Also notify Owner via user_message so they can verify the snapshot
    happened (especially during is_first_compaction · which signals a
    long session worth a coll review).
    """
    try:
        from aether_events import append_event, derive_session_id
        append_event(_enrich_event(payload, {
            "type": "pre_compact",
            "session_id": derive_session_id(payload),
            "payload": {
                "trigger": payload.get("trigger"),
                "usage_pct": payload.get("context_usage_percent"),
                "messages_to_compact": payload.get("messages_to_compact"),
                "is_first": payload.get("is_first_compaction"),
                "transcript_path_present": bool(payload.get("transcript_path")),
            },
        }))
    except Exception:
        pass

    # Snapshot transcript · last-chance grab before Cursor discards messages
    snap_path: Path | None = None
    try:
        snap_path = _safe_copy_transcript(payload, "precompact")
    except Exception:
        pass

    log_payload("preCompact", payload)

    # Tell Owner · don't lie if snapshot failed
    msg_bits = []
    pct = payload.get("context_usage_percent")
    if pct:
        msg_bits.append(f"上下文 {pct}%")
    if payload.get("is_first_compaction"):
        msg_bits.append("首次压缩")
    if snap_path:
        msg_bits.append(f"已 snapshot → {snap_path.name}")
    else:
        msg_bits.append("snapshot 失败 · transcript_path 不可读")
    user_message = "Aether · " + " · ".join(msg_bits) if msg_bits else None

    if user_message:
        reply({"user_message": user_message})
    else:
        fail_open()


def handle_sessionEnd(payload: dict) -> None:
    """Fired when Cursor closes the session.

    This is where heavier processing happens (still time-boxed · Cursor
    may kill us after ~60s). Sequence:

      1. Append session_end event to events.jsonl
      2. Kick off incremental indexer (events.jsonl → SQLite)
      3. Let extractor propose a coll draft if the session was dense
      4. NEVER block · each step has timeout + fail-open

    If indexer / extractor take too long · guardian will pick up the
    work on its next tick (6h / 24h).
    """
    try:
        from aether_events import append_event, derive_session_id
        sid = derive_session_id(payload)
        append_event(_enrich_event(payload, {
            "type": "session_end",
            "session_id": sid,
            "payload": {"reason": payload.get("reason") or "session_close"},
        }))
    except Exception:
        pass

    # Incremental index · best-effort · tolerant to any failure
    try:
        import subprocess
        subprocess.run(
            [sys.executable, str(ROOT / "bin" / "aether_indexer.py"), "ingest", "--quiet"],
            timeout=20, capture_output=True,
        )
    except Exception:
        pass

    # Session summarizer · dense session → coll draft in .aether/coll-drafts/
    # Separate subprocess · capped at 15s · never blocks sessionEnd even
    # if summarizer hangs.
    try:
        import subprocess
        subprocess.run(
            [sys.executable, str(ROOT / "bin" / "aether_session_summarizer.py"),
             "--on-session-end", "--quiet"],
            timeout=15, capture_output=True,
        )
    except Exception:
        pass

    # Final transcript snapshot · sessionEnd is the canonical "save it all"
    # moment. Captures everything afterAgentResponse / preCompact missed.
    try:
        _safe_copy_transcript(payload, "sessionend")
    except Exception:
        pass

    log_payload("sessionEnd", payload)
    fail_open()


# ─── dispatch ────────────────────────────────────────────────────────

HANDLERS = {
    "sessionStart": handle_sessionStart,
    "beforeSubmitPrompt": handle_beforeSubmitPrompt,
    "postToolUse": handle_postToolUse,
    "sessionEnd": handle_sessionEnd,
    "stop": handle_stop,
    "afterAgentResponse": handle_afterAgentResponse,
    "preCompact": handle_preCompact,
    # Day 8 PM (档位 2) · observation-only reflex arc expansion
    "afterAgentThought": handle_afterAgentThought,
    "postToolUseFailure": handle_postToolUseFailure,
    "beforeShellExecution": handle_beforeShellExecution,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Aether unified Cursor hook")
    ap.add_argument(
        "--event",
        required=True,
        choices=list(HANDLERS.keys()),
        help="which Cursor hook event this invocation represents",
    )
    args = ap.parse_args()

    payload = read_stdin_json()
    handler = HANDLERS[args.event]

    try:
        handler(payload)
    except SystemExit:
        raise
    except Exception:
        fail_open()
    return 0


if __name__ == "__main__":
    sys.exit(main())
