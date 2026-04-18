<div align="center">

# ⟁ Aether Kit

### A better `.cursorrules`

**Weighted style fields for Cursor, Claude, any LLM — zero dependencies, MIT.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Install: 30s](https://img.shields.io/badge/Install-30_seconds-ff69b4.svg)](#install)
[![Works with](https://img.shields.io/badge/Works_with-Cursor_·_Claude_·_GPT-brightgreen.svg)]()
[![Version](https://img.shields.io/badge/version-0.4.1--kit-blue.svg)](./bin/aether.py)

**[Install](#install)** · **[What is a field?](./FIELDS.md)** · **[Presets](./PRESETS.md)** · **[Recipes](./recipes/)**

</div>

---

## 30 seconds

### 1. Install

**macOS / Linux**

```bash
git clone https://github.com/497810wsl/aether-kit ~/aether
cd your-project/
~/aether/bin/aether init
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/497810wsl/aether-kit $HOME\aether
cd your-project
& "$HOME\aether\bin\aether.cmd" init
```

### 2. Use a preset

Open Cursor in your project. In any chat, paste one line:

```
activate linus-torvalds=0.8, engineering-rigor=0.9, cold-to-warm=-0.2
```

That's the **code-reviewer** preset. 4 more in [`presets/`](./presets/):
`debugger` · `tech-writer` · `architect` · `researcher`.

### 3. Watch the difference

Same AI. Same question. Different output.

| Without Aether | With `linus=0.9, rigor=0.9` |
|---|---|
| *"Here are some suggestions: consider Promise.all... use parameterized queries..."* | **"Three bugs, one catastrophic. Line 3 is SQL injection. Fix it now. Everything else can wait."** |

---

## What is this?

**`.cursorrules` works until you try to compose rules.**

- *"Be concise AND thorough"* — the model picks one.
- *"Don't sound like LinkedIn"* — you can't write negation into a rulebook.
- *"Did the rule actually fire?"* — you don't know.

Aether fixes the three:

| | `.cursorrules` | **Aether** |
|---|---|---|
| Activation | hardcoded rulebook | `linus=0.9, ive=0.3` · tunable dials in `[-1, 1]` |
| Negation | can only say "do X" | `linkedin=-0.8` actively repels LinkedIn voice |
| Measurable | unknowable | `python tools/fingerprint.py` returns a math distance |

One line in your project. Your existing `.cursorrules` keeps working — Aether writes to a separate `.cursor/rules/aether.mdc`.

---

## Why it's simple

You don't memorize parameters. You pick a preset.

```
presets/
├── code-reviewer.preset    → severity-tiered code review
├── debugger.preset         → stack-trace + blast-radius mode
├── tech-writer.preset      → restrained, precise prose
├── architect.preset        → system thinking + trade-offs
└── researcher.preset       → recursive why · cite sources
```

Each preset is **one file** · **one line to paste** · **one workflow**.

See [PRESETS.md](./PRESETS.md) for how to pick, combine, and write your own.

---

## What you get (9 starter fields · MIT forever)

| Field | Type | Purpose |
|---|---|---|
| [`linus-torvalds`](./fields/linus-torvalds.field.md) | style | direct · severity-tiered · no hedge words |
| [`jony-ive`](./fields/jony-ive.field.md) | style | restraint · material · warm minimalism |
| [`nolan`](./fields/nolan.field.md) | style | non-linear · time-gradient · subtext |
| [`engineering-rigor`](./fields/engineering-rigor.field.md) | discipline | correctness · blast-radius · failure modes |
| [`cold-to-warm`](./fields/cold-to-warm.field.md) | temperament | tone dial from impersonal to warm |
| [`brainstorm`](./fields/brainstorm.field.md) | action | divergent · 10+ ideas before ranking |
| [`deep-thinking`](./fields/deep-thinking.field.md) | action | recursive why · question premises |
| [`research`](./fields/research.field.md) | action | fact-backed · source-cited |
| [`code-generator`](./fields/code-generator.field.md) | capability | matches project style · minimal · complete |

Want more? Premium fields (`staff-engineer`, `product-designer`, `borges`, `zhang-ailing`) are part of **Aether Pro** — see contact info at the bottom.

---

## CLI

```
aether init [--preset starter|minimal] [--integration cursor|claude|generic]
aether demo [--scenario code-review|debugging|writing]
aether fetch <field-id>
aether list
aether status
aether version
```

Zero dependencies · Python 3.8+ stdlib only · 870 lines · [`bin/aether.py`](./bin/aether.py).

---

## Verify it fires

Run [`tools/fingerprint.py`](./tools/fingerprint.py) on the AI's response before and after activation. A non-zero math distance = the field actually shifted the output distribution. No guessing, no vibes.

---

## FAQ

<details>
<summary><b>Does this replace .cursorrules?</b></summary>

No. Aether writes to `.cursor/rules/aether.mdc` as a separate file. Your existing `.cursorrules` keeps working alongside. `CLAUDE.md` — same deal, Aether appends a section without touching what you wrote.
</details>

<details>
<summary><b>What's "weighted"? Why floats?</b></summary>

A rule says "do X" or not. A field says "shift in direction X by amount 0.9". `linus=0.3` = a whisper of Linus's voice. `linus=0.9` = full Linus. Negative = actively repel. Rules can't do this; fields can.
</details>

<details>
<summary><b>Production ready?</b></summary>

CLI: solid. The 9 starter fields: real, each with 8+ named dimensions and severity rules. The broader ecosystem (evolution, species, memory) is being developed in the maintainer's full workspace. This kit ships only what's battle-tested for solo-engineer daily use.
</details>

<details>
<summary><b>Privacy?</b></summary>

100% local. The CLI hits `raw.githubusercontent.com` only when you run `aether fetch`. No telemetry, no account, no cloud. Your `.aether/` directory stays on your machine.
</details>

<details>
<summary><b>How is this different from `@rule-name` in Cursor?</b></summary>

Cursor rules fire on filename matches. Aether fields fire on user activation and can compose with weights. Different problems, different solutions. They can coexist.
</details>

---

## Contributing

Found a field that should exist? Write one and PR. See [CONTRIBUTING.md](./CONTRIBUTING.md).

---

## License & Contact

[MIT](./LICENSE) © 2026 · [@497810wsl](https://github.com/497810wsl)

- **WeChat**: `wsl497810` (fastest · collaboration · Pro)
- **GitHub Issues**: [aether-kit/issues](https://github.com/497810wsl/aether-kit/issues)
- **Live demo**: [82.156.228.168](http://82.156.228.168/)
- **Aether Pro** (premium fields · ¥99 / $14 / year): see live site pricing page

---

<div align="center">

*A better `.cursorrules`. Same AI. Measurable output.*
`aether init`

⟁

</div>
