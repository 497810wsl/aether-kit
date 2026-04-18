# 🛠️ Debugger Recipe

**Use when**: investigating mysterious failures, sporadic bugs, race conditions, "worked yesterday" problems.

---

## One-line activation

```
activate engineering-rigor=0.9, nolan=0.3, linus-torvalds=0.5, cold-to-warm=-0.1
```

## Install the fields

```bash
aether fetch engineering-rigor
aether fetch nolan
aether fetch linus-torvalds
aether fetch cold-to-warm
```

## What you get

- Hypothesis-driven investigation (not checklist soup)
- Each hypothesis paired with a way to **observe/verify** it
- Narrative framing that helps you think in event chains, not static checks
- Explicit **blast radius** and **rollback path** before any change
- Rejects lazy fixes ("just add more timeout", "restart it", "wrap in try-catch")

## Example prompts

```
activate engineering-rigor=0.9, nolan=0.3, linus-torvalds=0.5, cold-to-warm=-0.1

Our API gateway returns 504 intermittently. Upstream looks healthy.
We already tried: more logging, higher timeouts. Nothing helped.

What's going on?
```

```
activate engineering-rigor=0.9, nolan=0.3, linus-torvalds=0.5, cold-to-warm=-0.1

Flaky test. Passes locally, fails 10% of the time in CI.
Here's the test + setup: [paste]

Investigate.
```

```
activate engineering-rigor=0.9, nolan=0.3, linus-torvalds=0.5, cold-to-warm=-0.1

Production incident postmortem draft: [paste]

Walk me through the event chain and tell me what we're missing.
```

## Variants

**For deep-dive / root cause** (when you have time and need to really understand):

```
activate engineering-rigor=1.0, nolan=0.6, linus-torvalds=0.4, cold-to-warm=0
```

**For on-call triage** (you need a fix in 5 minutes, not insight):

```
activate engineering-rigor=0.9, linus-torvalds=0.9, cold-to-warm=-0.3
```

**For teaching a junior how to debug**:

```
activate engineering-rigor=0.8, nolan=0.5, jony-ive=0.4, cold-to-warm=+0.3
```

## Signal it's working

- Opens with a reframe ("you're looking in the right place, the bug isn't there")
- Lists 3–5 specific hypotheses, each with **observation method**
- Order of investigation is explicit (cheapest diagnostic first)
- Mentions blast radius and rollback even for diagnostic actions
- Tells you explicitly what *not* to do (anti-patterns like "add timeout")

## Signal it's not working

- Generic checklist of "things to check"
- No way to verify any of the hypotheses
- No prioritization — all checks feel equal weight
- Suggests "add more logging" without specifying what logs
  → Check your activation line or run `aether doctor`

---

## Pro tip: Chain with Code Reviewer

When you find the bug, switch recipes:

```
# After debugger identifies the root cause:
activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2

Here's the proposed fix: [paste]
Review it.
```

This transitions from "find" to "critique fix" — different modes, both valuable.

---

[← all recipes](./) · [report issue](https://github.com/497810wsl/aether/issues)
