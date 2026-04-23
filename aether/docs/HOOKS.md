# Aether Hooks · Design Rationale

> Day 12 (coll-0084): extracted from `.cursor/hooks.json` meta-keys into a
> proper doc. Hooks.json is config · this is documentation. Changes to
> hook roles go HERE · not inline in the JSON. Installer output (from
> `aether_install.py · hooks_json_shared()`) also stays lean.

## Architecture · 3 layers

| Layer | Role | Storage |
|-------|------|---------|
| A · Truth | Markdown + JSON · Owner-authored decisions | `aether/`, `.aether/tasks.jsonl`, `.aether/handover/` |
| B · Index | SQLite full-text · rebuildable from A | `.aether/index.db` |
| C · Reflex | These hooks · write-only · never decide | `.cursor/hooks.json` |

Layer C **never makes decisions**. It captures events · appends to
`.aether/events.jsonl` · kicks maintenance. All judgment happens in
Layer A (Owner + AI reading docs) or Layer B (full-text search).

## Scheduling strategy · zero OS dependency

**No Windows Task Scheduler · no systemd · no cron · no daemon · no
background process pinning.**

The reflex arc is driven by three Python triggers:

1. **`sessionStart` hook** runs `aether_guardian.py --once` on every
   Cursor session open · one heartbeat per conversation.
2. **`sessionEnd` hook** runs `aether_hook.py sessionEnd` which chains
   `indexer_ingest` + `session_summarizer --on-session-end` +
   transcript snapshot to `.aether/transcripts/`.
3. **Autopilot module** (`aether_autopilot.py`) lazy-triggers guardian
   whenever Owner invokes ANY aether CLI (query / events / selfcheck
   / summarizer). Every CLI call = one free heartbeat.

**Owner's finger on the keyboard IS the scheduler.** Works identically
on Windows / macOS / Linux.

## Hook inventory · why each exists

### `sessionStart` · timeout 30 + 20
Two commands · `aether_hook.py --event sessionStart` + `aether_guardian.py --once`.
The hook emits `additional_context` via `aether_handshake.build_briefing(payload)`
so the AI gets pact + 5-mode + last-3-coll + today's handover in its
first message. Guardian tick piggybacks on session open.

### `postToolUse` · timeout 5
One event per tool call. Cheap. Feeds `events.jsonl` with the AI's
working style (which tools · how often · shapes).

### `afterAgentResponse` · timeout 5 (Day 8 PM)
Captures every assistant message text into events.jsonl + saves
decision-shaped responses (containing P0/P1, ##, decisions, commitments)
to `.aether/agent-responses/`. This is the **fix for "AI must remember
to write coll"** — coll-draft generation no longer depends on AI
self-discipline. Combined with sessionEnd's summarizer, every dense
conversation gets a draft.

### `preCompact` · timeout 10 (Day 8 PM)
**Last-chance snapshot** before Cursor compacts (and effectively
forgets) old messages. Copies `transcript_path` content to
`.aether/transcripts/precompact-*.md` and notifies Owner via
`user_message` that the snapshot was taken · or honestly says it
failed.

### `afterAgentThought` · timeout 5 (Day 8 PM · 档位 2)
Captures thinking-block **metadata only** (length + duration_ms +
model) · **never the thinking text itself**. Privacy-by-default:
thoughts may contain raw essence-style content. Downstream value:
critic / mirror_digest can correlate think-time with reaction
outcomes without storing thinking text.

### `postToolUseFailure` · timeout 5 (Day 8 PM · 档位 2)
The missing **failure** reflex arc — without it, AI's tool failures
(Shell errors, Read timeouts, Permission denied) are completely
invisible. Logs `failure_type + error_message[:200] + is_interrupt +
duration`. Enables "AI is stuck on X" pattern detection.

### `beforeShellExecution` · timeout 5 (Day 8 PM · 档位 2)
**Observation-only** shell command logger — we ALWAYS allow
(`permission: allow`). Goal is data: which shell commands does AI
actually run on Windows? Gold for evolving the `windows-shell` skill.
Logs `cmd_head + cmd_digest[:80] + cwd_short`. Never blocks · never
denies.

### `sessionEnd` · timeout 60
Chains `indexer_ingest` + `session_summarizer --on-session-end` +
transcript archive. This is where most of the per-session consolidation
work happens. 60s budget because transcript can be multi-megabyte.

### `stop` · timeout 30
Captures intermediate stop events (AI waiting on Owner · Owner
cancelled mid-turn). Lightweight.

## Why no `beforeSubmitPrompt`

Cursor docs say `beforeSubmitPrompt` only accepts `{continue,
user_message}` as output. **No `updated_input` / prompt rewrite is
supported** by Cursor's hook contract. We tried · Cursor silently
dropped our `{updated_input, input, prompt}` fields.

Compounded by Anthropic GitHub #48009 (`UserPromptSubmit` hooks
receive empty stdin on Windows) · this event is effectively useless
on Windows for our purpose.

Status line enforcement now lives in `.cursor/rules/aether.mdc` RULE 00
(`alwaysApply: true`) which is the only reliable cross-platform
mechanism Cursor provides.

## Budget summary

| Hook | Budget | Failure mode |
|------|--------|--------------|
| sessionStart | 30s + 20s (guardian) | fail-open |
| postToolUse | 5s | fail-open |
| afterAgentResponse | 5s | fail-open |
| afterAgentThought | 5s | fail-open |
| postToolUseFailure | 5s | fail-open |
| beforeShellExecution | 5s | fail-open (allow) |
| preCompact | 10s | fail-open |
| sessionEnd | 60s | fail-open |
| stop | 30s | fail-open |

**All hooks fail-open**. If Python is broken / Cursor misbehaves /
disk is full · the user's session is never blocked. Aether becomes
read-only; Owner keeps working.

## Data isolation

Hooks honor `payload.workspace_roots` from Cursor. `events.jsonl` /
`transcripts/` / `agent-responses/` go to **`<target-project>/.aether/`**
(per `aether_events.resolve_overlay_dir`), NOT central's `.aether/`.
This is the Day 9-10 federated-memory model.

## Evolution

Adding a new hook?
1. Implement handler in `aether_hook.py · handle_<event>()`.
2. Add entry to `.cursor/hooks.json` under `hooks.<event>` and to the
   generator in `aether_install.py · hooks_json_shared()`.
3. Document its role in THIS file (pick the matching section).
4. Run `aether install --global --check` + `aether selfcheck` to
   verify coverage.

Removing a hook?
1. Mark it deprecated here for one generation.
2. Remove from generator.
3. Next `aether install --global --apply` overwrites the user's config.
