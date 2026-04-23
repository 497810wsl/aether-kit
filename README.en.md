<div align="center">

# ⟁ Aether

### Cross-session memory for Cursor

**Your Cursor chats forget everything between sessions. Aether doesn't.**

[![License: PolyForm NC 1.0.0](https://img.shields.io/badge/License-PolyForm_NC_1.0.0-yellow.svg)](https://github.com/497810wsl/aether-kit/blob/main/LICENSE)
[![Works with](https://img.shields.io/badge/Works_with-Cursor-brightgreen.svg)](https://cursor.com)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)]()
[![Install: 5 min](https://img.shields.io/badge/Install-5_minutes-ff69b4.svg)](#install)

**[Install](#install) · [What it does](#what-it-does) · [Honest status](#honest-status) · [中文](./README.md)**

</div>

---

## What it does

Cursor starts every chat with a blank brain. If you opened Cursor yesterday and made 30 architectural decisions, today's chat doesn't know about them. You spend the first 10 minutes copy-pasting context, or you don't bother and the AI suggests things you already rejected yesterday.

Aether fixes this. When you open a new chat, a `sessionStart` hook runs. It reads your last handover, last 3 decision logs (collapses), your pact file, and the 5-mode activation rules — and injects them as `additional_context` for the AI. The AI's first reply already knows where you left off.

That's the whole pitch. One capability. No accounts. No cloud. Your data never leaves your machine.

---

## Honest status

Before you scroll down — these are the real numbers today:

| Metric | Value | What it means |
|---|---|---|
| GitHub stars | **0** | No one outside the author has validated this yet |
| Paying users | **0** | There's no paid tier |
| Days old | ~12 | Built solo, in public, from a spec |
| Production users | **1** (the author) | Daily use, n=1 |
| External contributors | **0** | PRs welcome |

If that concerns you, come back in 30 days. If it doesn't — read on.

---

## Who this is for

**It's for you if:**

- You use Cursor or Claude Code every day for the same project(s)
- You've hit the "new chat, re-explain context" wall more than once
- You're okay running one Python script per new IDE session
- You want to watch a dev tool evolve without marketing fluff

**It's not for you if:**

- You use Cursor casually / across many small projects
- You want a team collaboration tool (this is single-user)
- You need GUI / web dashboard (Aether is CLI + IDE hooks only)
- You expect a polished v1.0 today — this is week-2 work in public

---

## What Aether gives you

| Feature | Works today | What it actually does |
|---|---|---|
| **Session handshake** | ✅ | New chat reads your last handover + last 3 decision logs · AI's first reply already has context |
| **9 IDE hooks** | ✅ | `sessionStart` / `stop` / `postToolUse` / etc. · captures every meaningful event to `.aether/events.jsonl` |
| **Per-project isolation** | ✅ (Day 12) | Project A's memory doesn't leak into Project B · each project has its own `.aether/` overlay |
| **5-mode auto-activation** | ✅ | Say "review this code" → AI silently loads a code-review persona · no manual prompt prefix |
| **Language match** | ✅ (Day 12) | User writes Chinese → AI replies Chinese · English → English · no ceremony |
| **Honest self-check** | ✅ | `aether selfcheck --honest` shows not just "are files present" but "do I have external users yet" |
| **npm package** | 🚧 | Planned · today install via `git clone` |
| **Team sync** | ❌ | Single-user only by design |

---

## Install

Requires Python 3.9+ and Cursor.

### 1. Clone

```bash
git clone https://github.com/497810wsl/aether-kit ~/aether
```

### 2. Install globally (any Cursor session picks it up)

```bash
cd ~/aether
python aether/bin/aether_install.py --global --apply
```

This writes `~/.cursor/hooks.json` + `~/.cursor/rules/aether.mdc`. Your existing Cursor config is backed up to `.bak` before being touched.

### 3. Restart Cursor, open any project, start a new chat, say `你好` or `hi`

The AI's first reply must start with a line like:

```
⟁ Aether · Day 12/30 · 86/100 (32 ok · 2 warn · 3 fail) · scope: dev-self · handover: day-11-handover.md
```

(For a fresh project that hasn't registered with Aether, you'll see `unregistered` instead of `Day N/30` — run `aether project init --apply` inside that project to register it.)

If you see the status line, Aether is running. If you don't, check [troubleshooting](./docs/USING-IN-OTHER-PROJECTS.md#5--排错).

### 4. (Optional) Register a specific project

In any project folder:

```bash
aether project init --apply
```

This creates `.aether/` in that project · gives it its own handover log · Day counter · task ledger. Safe to run · safe to uninstall later (`aether project uninstall --apply`).

---

## What you'll see

**First new chat in a registered project**, AI's reply opens with:

```
⟁ Aether · Day 3/30 · ?/? · scope: guest @ my-project · handover: day-2-handover.md
```

- `Day 3/30` = third day of you working on this project with Aether watching
- `scope: guest @ my-project` = you're in `my-project`, not Aether's own dev repo
- `handover: day-2-handover.md` = AI already read your day-2 handover · knows what you were doing

After that, the conversation continues normally. The AI doesn't ask "where did we leave off?" because it already knows.

**End of day**, one command writes tomorrow's entry point:

```bash
aether daily write
```

This generates `day-N-handover.md` summarizing today's events. Next chat reads it. Memory is continuous.

---

## What Aether is NOT

- ❌ **Not a replacement for Cursor.** It sits on top as hooks + rules.
- ❌ **Not a better LLM.** Same AI, same quality — just with memory.
- ❌ **Not a prompt library.** It doesn't rewrite your prompts; it gives the AI session context.
- ❌ **Not a "weighted fields" framework.** (Earlier drafts of Aether led with that · form α retired it from the main pitch. Fields still exist for power users · just not the headline.)
- ❌ **Not a disruption.** 12 days old, 1 author, 0 external validation. See [scope reaffirmation](https://github.com/497810wsl/aether-kit/blob/main/labs/chronicle/scope-reaffirmation-2026-04-22.md) for the author's own brutal reality-check.

---

## FAQ

<details>
<summary><b>Will Cursor add this natively and make Aether obsolete?</b></summary>

Maybe. Cursor Desktop already has some memory features. If they ship full session handshake natively, Aether's core value shrinks. That risk is real · it's in the repo's [WHY-NOT.md](./docs/WHY-NOT.md). The author's bet: there's 6-18 months where Aether does this better than whatever Cursor ships next, and that window is worth something even if it closes.

</details>

<details>
<summary><b>Will you store my code / prompts anywhere?</b></summary>

No. Zero cloud. Zero telemetry. Zero accounts. `.aether/events.jsonl` stays on your disk · same for handover files · same for collapse logs. You can inspect everything with any text editor. `aether project uninstall --apply` removes everything cleanly.

</details>

<details>
<summary><b>What's "handover" / "collapse" / "dev-self" — is this a cult?</b></summary>

Vocabulary, not dogma. **Handover** = end-of-day memo for your next self. **Collapse** = decision log for a meaningful choice. **dev-self** = the scope where you're developing Aether itself vs. using it in another project. The words are replaceable — we kept them because rewriting them would break existing users' muscle memory. If you hate them, `grep -r "collapse" .` and rename.

</details>

<details>
<summary><b>Can I use this without the "pact" / "30-day experiment" framing?</b></summary>

Yes. The 30-day framing is the **author's** commitment to himself · not yours. Delete `labs/chronicle/collaboration-pact-2026-04-17.md` · the rest still works. Status line will fall back to "Day 1" on a freshly registered project · advances as you write handovers.

</details>

<details>
<summary><b>Python 3.9+? Why?</b></summary>

Walrus operator + type hints + `pathlib` in hooks. No external deps — pure stdlib. If you have Cursor, you probably have Python. If you don't, `brew install python@3.11` / `winget install Python.Python.3.11` and you're set.

</details>

<details>
<summary><b>Does this work on Windows / Linux / Mac?</b></summary>

All three. Tested daily on Windows. PowerShell-aware path handling · LF/CRLF mostly handled. File an issue if a hook misfires on your platform.

</details>

---

## Feedback, please

If you install this and have **any** reaction — "this is useful", "this is noise", "the hero line didn't make sense", "it broke on day 2" — open a GitHub issue. One star is public validation. One "this didn't work for me" issue is more valuable to the author right now than a silent install.

**Explicit success criteria for this project, today (Day 12 of 30):**

- 1 unaffiliated developer stars this repo → **win**, continue to Day 30+
- 5 developers manually invited by the author try it → **win**, same
- 30 days pass, 0 external users → **archive** · lessons published as methodology post

---

## Contact

- **WeChat**: `wsl497810` (mention "Aether" in first message)
- **GitHub Issues**: <https://github.com/497810wsl/aether-kit/issues>
- **Discussions**: <https://github.com/497810wsl/aether-kit/discussions>

---

## License

[**PolyForm Noncommercial 1.0.0**](./LICENSE) © 2026 · [@497810wsl](https://github.com/497810wsl)

- ✅ **Allowed** · personal / research / hobby / nonprofit use · modify · distribute (must preserve `Required Notice`)
- ❌ **Not allowed** · commercial use (including in-company internal use)
- 🏢 **Commercial license** · contact `wsl497810` on WeChat

**Why not MIT**: Aether is a solo-author project. The intent is "free to use, not free to bundle into commercial products". Non-commercial use is fully free · commercial use requires contacting the author first.

---

<div align="center">

*Cross-session memory for Cursor. Your AI stops forgetting. That's it.*

⟁

</div>
