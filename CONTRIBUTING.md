# Contributing to Aether Kit

Short version: **yes, please, and thank you**.

---

## What this repo accepts

✅ **New fields** · `.field.md` files following the 4-part anatomy in [FIELDS.md](./FIELDS.md)
✅ **New presets** · activation strings in `.preset` files, with attached evidence
✅ **Bug fixes** · CLI bugs, field typos, docs typos, install issues
✅ **Documentation** · improved READMEs, tutorials, translations
✅ **Troubleshooting entries** · symptoms + fixes seen in the wild

---

## What this repo doesn't accept (yet)

❌ **Philosophy / manifesto edits** — the kit is a **tool**, not a worldview
❌ **Unverified fields** — every field needs at least one before/after example
❌ **Heavy dependencies** — 0 dependencies is a feature, not a bug
❌ **UI / web-app features** — kit is CLI; browser frontends live elsewhere
❌ **LLM API clients** — kit is LLM-agnostic; bring your own Cursor/Claude/whatever

---

## How to submit a field

### 1. Copy an existing field as template

```bash
cp fields/linus-torvalds.field.md fields/your-field-id.field.md
```

### 2. Fill in the 4 sections

- **Frontmatter**: `field_id`, `type`, `version: 1`
- **Concentration vector**: 6–12 named dimensions with weights
- **Behavior**: what changes at > 0.5, at > 0.7
- **Composition + instructions**: stacking rules + literal AI directives

### 3. Write a test case

Include in the PR body:
- The question you asked
- The default AI's answer (without activation)
- The AI's answer with `activate your-field-id=0.85`
- Why the difference matters

### 4. Run fingerprint

```bash
python tools/fingerprint.py --before default.txt --after activated.txt
```

Paste the distance number in the PR. If < 0.2, your field isn't shifting the distribution meaningfully — tune the weights up.

### 5. Open the PR

- **Title**: `feat: add <field-id> field · <one-line description>`
- **Body**: include the 4 items above
- **Review**: expect 1–3 days turnaround for first-time contributors

---

## How to submit a preset

### 1. Create a `.preset` file

```
presets/your-preset-id.preset
```

Format:

```
# Human-readable name
# One-line description of when to use it

activate field-id=0.N, field-id=0.N, ...
```

### 2. Attach before/after evidence

One real task · before-preset output · after-preset output. Redact PII as needed.

### 3. Open the PR

Same format as field PRs.

---

## Style guide

- **Fields in English** for widest reach · mandarin translations as separate files welcome
- **Prefer nouns over adjectives** in dimension names (`severity_tier` not `severely_tiered`)
- **Weights in [0, 1] for positive / [-1, 0] for repulsion** · stay within the range
- **Decay rate**: 0.03 for discipline fields, 0.05 for style fields
- **Line length**: ≤ 100 chars · keep files diff-friendly

---

## Code of conduct · short form

- Be direct, not rude
- Disagreement is fine; personal attacks are not
- Cite sources when making empirical claims
- If a maintainer says "not now", accept gracefully; open an issue to discuss

---

## Maintainer response times

Realistic expectations:

| | Response |
|---|---|
| Simple typos / docs | 1 day |
| New field / preset | 1–3 days |
| New CLI feature | 3–7 days (may request discussion first) |
| Architecture changes | Open an issue first; PR after agreement |

One maintainer, real life. Patience appreciated.

---

## Questions before contributing

- Tiny: open an issue
- Medium: WeChat `wsl497810`
- Large / architectural: open a discussion

---

*See also*: [README.md](./README.md) · [FIELDS.md](./FIELDS.md) · [PRESETS.md](./PRESETS.md)
