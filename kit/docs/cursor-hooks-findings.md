# Building PROTOCOL 0 for Cursor · what we learned about hooks

> A field report from shipping `aether-kit` v0.4.3 · 2026-04-19
> 8 commits · 5 wrong assumptions · 2 platform-level blockers · 1 working architecture

We wanted to give every Cursor session in any workspace **automatic cross-session memory** — open Cursor, the AI knows what day of the project it is, what was decided yesterday, and what's queued for today. No typing `aether handshake`. No manual context paste.

We knew Cursor had hooks. We figured: just intercept the user's prompt, prepend the context, done.

It took us 8 commits and a Saturday afternoon to learn that's not how it works. This document is what we wish we'd known on commit 1.

---

## TL;DR for impatient readers

1. **Cursor's `beforeSubmitPrompt` hook does NOT support prompt rewriting.** Its only output fields are `{continue, user_message}` — you can block submission, you cannot modify it. We learned this from line 1164 of [cursor.com/docs/agent/third-party-hooks](https://cursor.com/docs/agent/third-party-hooks). Our `updated_input` / `prompt` fields were silently dropped.
2. **On Windows, `beforeSubmitPrompt` hooks receive empty stdin** ([Anthropic Claude Code GitHub #48009](https://github.com/anthropics/claude-code/issues/48009), closed as duplicate of #36156). The whole event is currently broken on Windows · stdin pipe inheritance issue · affects `claude-mem` and others.
3. **`additional_context` returned from `sessionStart` is a soft hint, not a hard rule.** Top-tier models (we tested with claude-opus-4-7-thinking-max) sometimes ignore it for trivial inputs ("hi", "你好", an emoji).
4. **The only reliable cross-platform mechanism** for behavioural enforcement is `sessionStart` → `additional_context` **paired with** a `~/.cursor/rules/*.mdc` rule file marked `alwaysApply: true`. The hook injects the data, the rule forces the behaviour.

If you're building a Cursor hook system, start there. Skip the prompt-rewriting rabbit hole.

---

## What we tried

### Attempt 1 · `sessionStart` + `additional_context` (commit `69fef7c`)

Naive approach. Hook reads stdin, builds a markdown briefing, returns:

```python
{"additional_context": "# Aether handshake\n\nDay 6/30 · health 100/100 · ..."}
```

**Result:** Hook fires (Cursor's hook log confirms `executed successfully`). Briefing is in the AI's context (we can see it in the log's OUTPUT block). But when the user types "你好" the AI replies with a friendly greeting and **never mentions the briefing**. When the user asks "今天 Day 几" the AI **does** quote the briefing.

**Diagnosis:** `additional_context` is reference material, not instruction. The model decides whether to surface it based on conversational relevance. Trivial greetings don't trigger it.

### Attempt 2 · Strengthening with a `RULE 00` (commit `447d18a`)

We added a rule file at `.cursor/rules/aether.mdc`:

```markdown
---
alwaysApply: true
---

## RULE 00 · Status line pass-through (UNCONDITIONAL)

If `additional_context` contains a line matching `^⟁ Aether · Day \d+/30 · ...$`,
your FIRST response in this session MUST start with that line verbatim,
inside a fenced code block, before any greeting / question / answer / tool use.

No exception for trivial inputs (`hi` / `你好` / `?` / emoji).
```

**Result:** Better. The model now reliably quotes the line for substantive questions. Still skipped occasionally for very short replies. The rule is working but the model has wiggle room.

### Attempt 3 · The "real" rewriter via `beforeSubmitPrompt` (commit `f691e43`)

We thought: forget soft hints. Use `beforeSubmitPrompt` to literally rewrite the user's prompt before the AI sees it. Inject the status line as the first line of what the AI receives. Zero compliance risk.

```python
def handle_beforeSubmitPrompt(payload):
    user_prompt = payload.get("prompt", "")
    new_prompt = f"⟁ Aether · Day {day}/30 · ...\n\n---\n\n{user_prompt}"
    reply({
        "permission": "allow",
        "updated_input": new_prompt,
        "input": new_prompt,    # try multiple field names
        "prompt": new_prompt,   # since spec is unclear
    })
```

**Result:** Cursor logged `Hook 1 executed successfully and returned valid response`. The OUTPUT block in the hook log showed our JSON. But the AI received the **original** prompt, not our rewritten one.

We thought we had the wrong field name. We didn't.

### The reality check (commit `9a0bff9`)

Read the docs. Carefully. Line 1164 of `cursor.com/docs/agent/third-party-hooks`:

```
beforeSubmitPrompt
Called right after user hits send but before backend request. Can prevent submission.

Output Fields:
  continue       boolean        Whether to allow the prompt submission to proceed
  user_message   string (opt)   Message shown to the user when the prompt is blocked
```

**Two fields. Neither rewrites.** `beforeSubmitPrompt` is a gate, not a transformer. Cursor accepted our JSON because it parses successfully — but it ignored the `updated_input`/`input`/`prompt` fields because they're not in the schema for that event.

Then we found [Anthropic GitHub #48009](https://github.com/anthropics/claude-code/issues/48009): on Windows, this hook receives empty stdin anyway. We couldn't have read the prompt to rewrite it even if rewriting were supported.

We pivoted back to Attempt 1 + 2 (sessionStart + RULE 00) and accepted that's the architecture.

---

## The 5 wrong assumptions

| # | Assumed | Reality |
|---|---|---|
| 1 | `additional_context` makes the AI follow instructions | It's a reference, not a directive · models comply variably |
| 2 | `beforeSubmitPrompt` accepts `updated_input` like `preToolUse` does | Cursor docs explicitly limit it to `{continue, user_message}` |
| 3 | If Cursor accepts our JSON without error, it's using all the fields | Unknown fields silently dropped · check the log to see what reached the model |
| 4 | Windows Python `sys.stdin.read()` works the same as Linux/macOS | On Windows, console codepage (cp936 on Chinese Windows) corrupts UTF-8 · use `sys.stdin.buffer.read()` and decode manually |
| 5 | If hook runs and exits 0, the user-visible behaviour will reflect what we returned | Hook protocol level success ≠ behavioural compliance · always verify visually in a real Cursor session, not just in the hook log |

---

## The architecture that actually works

```
                     Cursor sessionStart
                            ↓
         python ~/.cursor/hooks/aether-dispatch.py
                            ↓
         reads stdin · finds workspace_roots[0]
                            ↓
   workspace has aether/bin/aether_hook.py?
            ↙ YES                ↘ NO
  exec project hook              return {}
            ↓                    (zero effect on
  inject briefing                 non-Aether projects)
  with status line
            ↓
   ~/.cursor/rules/aether.mdc (alwaysApply: true)
            ↓
  RULE 00 instructs AI: quote the status line verbatim
  as the first line of your first response
            ↓
   User types "你好"
            ↓
   AI replies:
   ```
   ⟁ Aether · Day 7/30 · 100/100 · handover: day-6-handover.md
   ```
   你好 ...
```

Three properties matter:
1. **Cross-platform.** Single Python entry point. No PowerShell wrappers. Same code on Windows, macOS, Linux.
2. **Cross-project.** Global hook at `~/.cursor/`. Per-project opt-in by presence of `aether/bin/aether_hook.py`. Non-Aether workspaces unaffected.
3. **Visible verification.** The status line on the AI's first response is the only proof the user needs that the hook fired correctly. No silent failures.

---

## Install in 30 seconds

```bash
git clone https://github.com/497810wsl/aether-kit ~/aether-kit
~/aether-kit/scripts/install-hook.sh        # macOS / Linux
# or:
& "$HOME\aether-kit\scripts\install-hook.ps1"   # Windows PowerShell
```

Restart Cursor. Done.

The installer is **idempotent** (safe to run multiple times) and **non-destructive** (preserves any existing `~/.cursor/hooks.json` entries you have). Uninstall with `uninstall-hook.{sh,ps1}` — strips the Aether entry, leaves your other hooks intact.

---

## Takeaways for anyone building Cursor hooks

If you've read this far you're probably writing your own hook. Three things we wish someone had told us:

### 1. Read the docs by event, not by overview

The docs page is ~1400 lines. The overview ("hooks let you observe, control, and modify behavior") is misleading per-event. Each event has a specific input shape and a specific output shape. Search the page for your event name. The Cursor docs are the source of truth · GitHub issues / forum posts are catching-up commentary.

### 2. Always look at the hook log

`%APPDATA%\Cursor\logs\<timestamp>\<window>\<output>\cursor.hooks.workspaceId-<id>.log`(Windows) or `~/Library/Logs/Cursor/.../cursor.hooks.workspaceId-*.log` (macOS).

It shows the **exact INPUT Cursor sent your hook** and the **exact OUTPUT Cursor received from your hook**, with timestamps. If your hook isn't behaving, the log tells you whether the problem is on your side (bad output) or Cursor's side (your output ignored).

This is how we discovered Cursor was silently dropping our `updated_input` field — the log showed our JSON arriving correctly, but the AI received the original prompt.

### 3. Test in a real Cursor session, not just by piping JSON to your script

Hook protocol-level success (exit 0, valid JSON) is not the same as user-visible success. The model has to actually use what you injected. The only way to verify is to type a real prompt in Cursor and see what comes back.

We had a moment where our hook was returning a perfect 3,191-character briefing for two days, but trivial chats showed nothing. Local testing said success. Cursor session said failure. Trust the session.

---

## Status of `beforeSubmitPrompt` rewrite (as of 2026-04-19)

If you came here Googling "Cursor beforeSubmitPrompt updated_input" or "Cursor hooks rewrite user prompt" — short answer:

- **Not supported by Cursor** as of v3.1.15 (the schema explicitly omits it).
- **Anthropic Claude Code** has the same event (`UserPromptSubmit`) and the same gating-only contract.
- **Windows stdin bug** (#48009) means even a future rewrite-capable spec wouldn't work on Windows until pipe inheritance is fixed.

If you need prompt rewriting today, your options are:
1. Wait for Cursor to add `updated_input` to `beforeSubmitPrompt` (no public roadmap signal that we found).
2. Use `sessionStart` + a strong rule file (what we did · imperfect but works).
3. Build a pre-Cursor IDE-side wrapper that intercepts the prompt before it reaches Cursor (heavy · platform-specific · we did not pursue).

---

## What we shipped

[`aether-kit` v0.4.3](https://github.com/497810wsl/aether-kit) · MIT · cross-platform.

The hook system is **separable** from the rest of Aether (fields, presets, fingerprint). If you want only the cross-session memory layer for your own Cursor projects, you can copy `kit/.cursor-global/` and the install scripts and ignore everything else.

The 8-commit history is preserved in the repo. If you're learning hooks, the diffs themselves are educational — you can see the exact wrong assumptions we made and how they got corrected.

---

## Contact

- Issues / PRs: [aether-kit/issues](https://github.com/497810wsl/aether-kit/issues)
- WeChat: `wsl497810`
- Live demo: [82.156.228.168](http://82.156.228.168/)

If you're building Cursor infrastructure and hit a similar wall, reach out. Five wrong assumptions in one afternoon is plenty for one team — we'd rather you skip ours.

---

*Aether Kit · A better `.cursorrules` · with cross-session memory baked in.*
