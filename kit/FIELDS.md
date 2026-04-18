# What is a field?

If you've written `.cursorrules`, you've written **rules**. A rule is a command: "do X", "don't do Y".

A **field** is different. A field is a **vector of named dimensions with floating-point weights**.

---

## The 60-second picture

```
.cursorrules                        Aether field
────────────                        ─────────────
- Be direct                         linus-torvalds.field.md
- Use bullet points                 ├─ directness:      0.90
- Never use "maybe"                 ├─ hedge_aversion:  0.95
- Point out bugs first              ├─ severity_tier:   0.85
                                    ├─ bullet_density:  0.80
                                    └─ warmth:         -0.30

command · all-or-nothing            vector · dials at your resolution
```

You activate a field with a weight:

```
activate linus-torvalds=0.9
```

The 0.9 is a **global intensity**. Every dimension of the field fires at 0.9 × its own weight. So `linus` at 0.9 fires full Linus; `linus` at 0.3 fires a whisper of Linus.

---

## Why weights, why floats, why a vector?

Three problems rules can't solve:

### 1. Composition

Rules: `concise AND thorough`. The model picks one.

Fields: `concision=0.8, thoroughness=0.7`. Orthogonal dimensions · no fight · both fire.

### 2. Negation

Rules: you can't write "don't sound like LinkedIn" in a way that actually moves the needle.

Fields: `linkedin=-0.8`. Negative weight = **actively repel**. The output distribution shifts **away** from LinkedIn-shaped tokens. Rules can only block "do X"; fields can also express "do less X" and "do anti-X".

### 3. Measurability

Rules: did the model follow the rule? Nobody knows.

Fields: `tools/fingerprint.py` extracts palette, keywords, structure from the AI's output. Compare before-activation vs after-activation. Get a math distance. **Proven** shift.

---

## Anatomy of a `.field.md` file

Every field in [`fields/`](./fields/) has 4 parts:

```
┌─ 1. Frontmatter ─────────────────────────────────┐
│  field_id, type (style / discipline / action...), │
│  version, decay_rate, activation_count            │
└───────────────────────────────────────────────────┘

┌─ 2. Concentration vector ────────────────────────┐
│  A table of named dimensions with default weights │
│  (your `activate X=0.9` multiplies these)         │
└───────────────────────────────────────────────────┘

┌─ 3. Field behavior ──────────────────────────────┐
│  Thresholded rules:                               │
│    "When concentration > 0.5, do this"            │
│    "When concentration > 0.7, also do this"       │
└───────────────────────────────────────────────────┘

┌─ 4. Composition + AI instructions ───────────────┐
│  Which other fields stack cleanly                 │
│  Literal imperatives for the AI at runtime        │
└───────────────────────────────────────────────────┘
```

You can read any field file top-to-bottom in 3 minutes and know exactly what it does.

---

## Field types (at a glance)

| Type | What it changes | Example |
|---|---|---|
| **style** | how the AI sounds | `linus-torvalds`, `jony-ive`, `nolan` |
| **discipline** | how the AI analyzes | `engineering-rigor`, `research` |
| **action** | what the AI does first | `brainstorm`, `deep-thinking` |
| **temperament** | emotional tone | `cold-to-warm` |
| **capability** | domain skill | `code-generator` |

Fields of different types stack cleanly. Fields of the same type at high concentration can fight — that's noted in each field's "composition" section.

---

## "Do I have to know all this?"

**No.** Read [PRESETS.md](./PRESETS.md) and pick a preset. The preset was already designed by someone who understood the weights. You just paste one line.

This document is for when you're ready to write your own field or debug an unexpected output. Most users never need to come back.

---

## Writing your own field

Copy [`fields/linus-torvalds.field.md`](./fields/linus-torvalds.field.md) as a template. Edit the 4 sections. Save to your `.aether/fields/` — instantly usable. PR it to this repo if it's good; others may want it too.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the PR flow.
