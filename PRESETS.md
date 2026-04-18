# Presets · the fast lane

Don't memorize 9 fields and their weights. Pick a preset · paste the line · use.

---

## The 5 starter presets

| Preset | For | Activation line |
|---|---|---|
| [`code-reviewer`](./presets/code-reviewer.preset) | reading PRs, finding bugs | `activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2` |
| [`debugger`](./presets/debugger.preset) | stack-trace · root cause | `activate engineering-rigor=0.9, deep-thinking=0.6, nolan=0.3` |
| [`tech-writer`](./presets/tech-writer.preset) | docs · READMEs · changelogs | `activate jony-ive=0.7, engineering-rigor=0.5, cold-to-warm=0.3` |
| [`architect`](./presets/architect.preset) | system design · trade-offs | `activate engineering-rigor=0.8, nolan=0.5, deep-thinking=0.5` |
| [`researcher`](./presets/researcher.preset) | reading papers · citing sources | `activate research=0.8, deep-thinking=0.7, cold-to-warm=0.2` |

Copy. Paste in Cursor. Use.

---

## How to use a preset

### Method 1 · paste the line

Open the `.preset` file, copy the `activate` line, paste into your Cursor chat before your actual question.

```
activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2

@your-file.py  Review this.
```

### Method 2 · save as Cursor snippet

Cursor supports text snippets. Save each `activate ...` line as a snippet with a short trigger (e.g. `/reviewer`). Now one slash = one persona.

### Method 3 · Cursor rules reference

If you use Cursor's `Rules` panel, add a new rule file:

```
~/.cursor/rules/preset-reviewer.mdc

---
description: Aether · code-reviewer preset
---
Activate: linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2
```

Now Cursor can auto-suggest it based on filename or task.

---

## Stacking presets

Presets are just activation strings. You can stack:

```
activate linus-torvalds=0.8, engineering-rigor=0.9   # code-reviewer
activate research=0.6                                 # adds research rigor
```

Weights from the same field are overwritten by the last activation. Weights from different fields stack.

**Combined total weight should stay ≤ 2.0**. Above that, the model tends to lose coherence.

---

## Writing your own preset

A preset is just a text file. Format:

```
# Short human name
# One-line description

activate field-id=0.N, field-id=0.N, field-id=-0.N
```

Drop it in [`presets/`](./presets/) in your `~/aether/` install, or anywhere in your own project.

Good presets share:
- **≤ 4 fields** (each field pulls weight; over 4 starts to cancel out)
- **One action · one temperament · one discipline** typical shape
- **Negative weights sparingly** (-0.2 to -0.5 is enough; -0.8+ is nuclear)
- **Test** with `tools/fingerprint.py` before declaring it good

---

## Contributing a preset

Got one that works for you? PR it. See [CONTRIBUTING.md](./CONTRIBUTING.md). Be ready to attach:
- The preset file
- One real before/after example (redact as needed)
- One `fingerprint.py` run showing the math distance

Communities curate; maintainer merges.
