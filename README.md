<div align="center">

# ⟁ Aether Kit

### A better `.cursorrules`

**Weighted style fields for Cursor, Claude, any LLM — zero dependencies, MIT.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Install: 30s](https://img.shields.io/badge/Install-30_seconds-ff69b4.svg)](#30-seconds)
[![Works with](https://img.shields.io/badge/Works_with-Cursor_·_Claude_·_GPT-brightgreen.svg)]()
[![Version](https://img.shields.io/badge/version-0.4.3--kit-blue.svg)](./bin/aether.py)

**[Install](#30-seconds)** · **[What is a field?](./kit/FIELDS.md)** · **[Presets](./kit/PRESETS.md)** · **[Agents guide](./AGENTS.md)** · **[Recipes](./kit/recipes/)**

</div>

---

## Repo layout · 6 top-level items

```
aether-kit/
├── README.md      ← you are here · start here
├── AGENTS.md      ← contract for any AI that opens this repo
├── LICENSE        ← MIT
├── bin/           ← per-project CLI · `aether init` / `demo` / `fetch` / ...
│   ├── aether · aether.cmd · aether.py
├── scripts/       ← global-install helpers (new in 0.4.3)
│   ├── install-hook.{ps1,sh} · uninstall-hook.{ps1,sh}
└── kit/           ← all content · fields · docs · global-hook source
    ├── INSTALL.md · FIELDS.md · PRESETS.md · CONTRIBUTING.md · AGENTS.md
    ├── fields/         9 starter .field.md files (MIT forever)
    ├── presets/        5 one-line activation shortcuts
    ├── recipes/        example use cases
    ├── templates/      cursor rule template (used by `aether init`)
    ├── tools/          fingerprint.py · verify a field actually fired
    ├── demo/           showcase.json · powers `aether demo`
    ├── docs/           contact.md · Pro purchase flow
    └── .cursor-global/ source for global hook · copied to ~/.cursor/ by installer
```

**Why this layout?** Two rules:
- **Root is an index** (5 items · 4 seconds to orient)
- **`bin/` stays at root** so `~/aether/bin/aether init` keeps working, matching what was published before `v0.4.2-kit`

If you want to vendor this kit into your own monorepo as `vendor/aether-kit/` — great, the 5-item root keeps your directory listings clean.

---

## You just cloned the kit — now what?

**This repo is a toolbox that stays in one place.** Fields and the CLI live here. You **don't** drop this whole folder into each of your projects. Instead:

1. Clone this repo once, to a stable location (e.g. `~/aether`).
2. For each project where you want Aether, run `aether init` **from inside that project**. This creates a small `.aether/` folder (just config + field copies) and a `.cursor/rules/aether.mdc` rule — the only two things your project gains.
3. Your actual code stays untouched. Your existing `.cursorrules` keeps working.

**Two-location model at a glance**:

```
~/aether/                          ← the kit (this repo · stays put)
├── bin/aether.py                  ← CLI
└── kit/
    ├── fields/*.field.md          ← 9 starter fields
    └── presets/*.preset           ← 5 one-line activations

<your-project>/
├── .aether/fields/                ← created by `aether init` · small
└── .cursor/rules/aether.mdc       ← created by `aether init` · tells Cursor the rules
```

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

That's the **code-reviewer** preset. 4 more in [`kit/presets/`](./kit/presets/):
`debugger` · `tech-writer` · `architect` · `researcher`.

### 3. Watch the difference

Same AI. Same question. Different output.

| Without Aether | With `linus=0.9, rigor=0.9` |
|---|---|
| *"Here are some suggestions: consider Promise.all... use parameterized queries..."* | **"Three bugs, one catastrophic. Line 3 is SQL injection. Fix it now. Everything else can wait."** |

---

## Install globally (new in 0.4.3) · one hook · every workspace

The per-project install above gives you fields and presets. The **global hook** gives you something else: any workspace with an `aether/bin/aether_hook.py` file auto-handshakes on Cursor session start · no per-project hook config, no manual `handshake` keyword. Non-Aether workspaces stay completely untouched.

```powershell
# Windows · PowerShell
git clone https://github.com/497810wsl/aether-kit $HOME\aether-kit
& "$HOME\aether-kit\scripts\install-hook.ps1"
```

```bash
# macOS / Linux
git clone https://github.com/497810wsl/aether-kit ~/aether-kit
~/aether-kit/scripts/install-hook.sh
```

Then restart Cursor. The installer:

- Copies `aether-dispatch.py` to `~/.cursor/hooks/`
- Copies `aether.mdc` to `~/.cursor/rules/` (user-level rule · opt-out friendly)
- Merges the hook entry into `~/.cursor/hooks.json` (preserves any other user hooks you have)

To remove: `install-hook.ps1` → `uninstall-hook.ps1` (or the `.sh` variant).

### What the global hook does

On every new Cursor session, the dispatcher:

1. Reads Cursor's `workspace_roots[0]` from the event payload
2. Checks if that workspace contains `aether/bin/aether_hook.py`
3. **If yes** → execs the project's hook · injects its project-specific briefing (Day/health/handover/recent collapses) into `additional_context`
4. **If no** → returns `{}` · zero effect · you won't notice the hook is even installed

The companion rule (`~/.cursor/rules/aether.mdc`) tells the AI to quote a one-line status marker as the first line of its first response when a briefing is present · the visible signal that the hook fired.

**Safe to install if you only use Aether in one project** · all other Cursor workspaces behave exactly as before.

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
| Measurable | unknowable | `python kit/tools/fingerprint.py` returns a math distance |

One line in your project. Your existing `.cursorrules` keeps working — Aether writes to a separate `.cursor/rules/aether.mdc`.

---

## Why it's simple

You don't memorize parameters. You pick a preset.

```
kit/presets/
├── code-reviewer.preset    → severity-tiered code review
├── debugger.preset         → stack-trace + blast-radius mode
├── tech-writer.preset      → restrained, precise prose
├── architect.preset        → system thinking + trade-offs
└── researcher.preset       → recursive why · cite sources
```

Each preset is **one file** · **one line to paste** · **one workflow**.

See [kit/PRESETS.md](./kit/PRESETS.md) for how to pick, combine, and write your own.

---

## What you get (9 starter fields · MIT forever)

| Field | Type | Purpose |
|---|---|---|
| [`linus-torvalds`](./kit/fields/linus-torvalds.field.md) | style | direct · severity-tiered · no hedge words |
| [`jony-ive`](./kit/fields/jony-ive.field.md) | style | restraint · material · warm minimalism |
| [`nolan`](./kit/fields/nolan.field.md) | style | non-linear · time-gradient · subtext |
| [`engineering-rigor`](./kit/fields/engineering-rigor.field.md) | discipline | correctness · blast-radius · failure modes |
| [`cold-to-warm`](./kit/fields/cold-to-warm.field.md) | temperament | tone dial from impersonal to warm |
| [`brainstorm`](./kit/fields/brainstorm.field.md) | action | divergent · 10+ ideas before ranking |
| [`deep-thinking`](./kit/fields/deep-thinking.field.md) | action | recursive why · question premises |
| [`research`](./kit/fields/research.field.md) | action | fact-backed · source-cited |
| [`code-generator`](./kit/fields/code-generator.field.md) | capability | matches project style · minimal · complete |

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

Zero dependencies · Python 3.8+ stdlib only · ~920 lines · [`bin/aether.py`](./bin/aether.py).

---

## Verify it fires

Run [`kit/tools/fingerprint.py`](./kit/tools/fingerprint.py) on the AI's response before and after activation. A non-zero math distance = the field actually shifted the output distribution. No guessing, no vibes.

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

Found a field that should exist? Write one and PR. See [kit/CONTRIBUTING.md](./kit/CONTRIBUTING.md).

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
