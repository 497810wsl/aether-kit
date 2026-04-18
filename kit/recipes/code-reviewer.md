# 🔍 Code Reviewer Recipe

**Use when**: reviewing PRs, finding bugs fast, prioritizing by severity.

---

## One-line activation

```
activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2
```

## Install the fields

```bash
aether fetch linus-torvalds
aether fetch engineering-rigor
aether fetch cold-to-warm
```

## What you get

- Bugs ranked by severity (catastrophic > critical > bug > nit)
- Direct, unambiguous language — no "you could consider"
- Specific fixes, not vague suggestions
- Rejects anti-patterns like "add more logging" or "increase timeout"

## Example prompts

```
activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2

Review this function: [paste]
```

```
activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2

Review this PR diff. Rank issues by severity.
Blast radius matters more than style.
[paste diff]
```

```
activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2

This passed CI and code review but caused a prod incident.
What should the reviewer have caught?
[paste incident summary + code]
```

## Variants

**For hostile architecture reviews** (you really want to break a proposal):

```
activate linus-torvalds=0.95, engineering-rigor=1.0, cold-to-warm=-0.4
```

**For mentoring juniors** (still direct, but with empathy):

```
activate linus-torvalds=0.6, engineering-rigor=0.8, jony-ive=0.3, cold-to-warm=+0.3
```

**For quick scan** (skim for obvious issues, not deep review):

```
activate linus-torvalds=0.7, engineering-rigor=0.6
```

## What this recipe does *not* do

- **Doesn't teach.** If you want pedagogical review, bump `cold-to-warm` up and add `jony-ive`.
- **Doesn't write tests.** It points out missing tests; it doesn't draft them.
- **Doesn't refactor.** It criticizes; implementation is a different mode.

For those, chain with: `activate engineering-rigor=0.8, jony-ive=0.5` for refactor guidance.

## Signal it's working

- Critical bugs get their own section, not bullet points
- Language like "catastrophic", "dangerous", "fix now", "wrong assumption"
- Prioritized action list at the end ("fix X first, Y can wait")
- No "overall this looks good" filler

## Signal it's not working

- Vague phrases: "you might want to...", "it's a good idea to..."
- Everything is a bullet point at the same priority
- Closes with "looks good overall"
  → Your activation line might have been ignored. Check `.cursor/rules/aether.mdc` exists.

---

[← all recipes](./) · [report issue](https://github.com/497810wsl/aether/issues)
