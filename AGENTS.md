# AGENTS.md

> For any AI agent(Cursor / Claude Code / Copilot / etc.)reading this repository: read this file first.

---

## What this repo is

**Aether Kit** — a weighted style-field activation layer for LLM-backed coding tools (Cursor, Claude Code, any `.cursorrules`-reading editor).

Core idea: instead of writing flat rules (`"be concise"`), users activate **fields** — named, weighted style/discipline vectors — that shift the LLM's output distribution in a measurable way.

- `activate linus-torvalds=0.9` → AI becomes direct, severity-tiered, no hedge words
- `activate linkedin=-0.8` → AI actively repels LinkedIn-voice tokens
- `python tools/fingerprint.py` → proves with math that the activation fired

Zero dependencies. Python stdlib. MIT.

---

## Two-location install model (important)

This repo is **the kit** — the toolbox that stays in one place.
It does NOT get installed *into* user projects. User projects only receive two files:

```
~/aether/                            ← kit home (this repo, cloned once)
└── bin/aether.py                    ← CLI tool

(on `aether init` inside <project>/:)
<project>/.aether/                   ← per-project config + field copies
<project>/.cursor/rules/aether.mdc   ← Cursor rule that reads .aether/fields/
```

Agents: when the user asks "where do fields live in my project", the answer is `<project>/.aether/fields/`. **Do not** direct them to modify files inside the kit directory.

---

## Directory map

| Path | Role | Agents edit? |
|---|---|---|
| `bin/aether.py` | CLI entry point · handles `init`, `fetch`, `demo`, etc. | Yes, carefully |
| `bin/aether.cmd` | Windows PowerShell wrapper | Rarely |
| `fields/` | 9 MIT starter `.field.md` files | Yes, on PR |
| `presets/` | 5 pre-authored activation shortcuts | Yes, on PR |
| `templates/aether.mdc.template` | Rule template copied to user projects on `init` | Yes, carefully |
| `demo/showcase.json` | Scenario data for `aether demo` | Yes |
| `recipes/` | Ready-made use cases (markdown) | Yes |
| `tools/fingerprint.py` | Verification tool — proves field fired via math distance | Rarely |
| `docs/contact.md` | Owner contact + Pro purchase flow | Yes |
| `README.md` · `FIELDS.md` · `PRESETS.md` · `INSTALL.md` · `CONTRIBUTING.md` | Public docs | Yes |

---

## Working rules for agents editing this repo

1. **Keep zero dependencies.** No `pip install` asks. If you're reaching for one, stop and ask.
2. **Flat fields directory.** Do not re-create `gen4-morphogen/` or other deep path structures — that's the maintainer's private workspace convention, not the kit's.
3. **Respect the two-location model.** Changes to how fields install go in `bin/aether.py` (`do_init`). Changes to what gets copied into user projects go through `templates/aether.mdc.template`.
4. **Every field change needs a before/after.** If you add or modify a `.field.md` file, attach an observable output difference in the PR description.
5. **Style consistency.** Field files follow a 4-section anatomy (frontmatter · concentration vector · behavior thresholds · composition + AI instructions). See `FIELDS.md`.
6. **No philosophy creep.** This kit is a tool. Deep ontology / manifesto discussions belong in the maintainer's private workspace, not here.

---

## How to respond to common user questions

**"How do I install this into my project?"**
```bash
cd your-project/
~/aether/bin/aether init
```
Read `INSTALL.md` for the 3-step version.

**"What fields exist?"**
Point to `fields/` directory (9 MIT starters) and mention Pro fields require purchase via `docs/contact.md`.

**"How do I pick the right weights?"**
Start with a preset from `presets/`. Tune later. See `PRESETS.md`.

**"Will Aether prevent AI hallucination?"**
No. Aether shapes *style*, not *truth*. Fields like `engineering-rigor=0.9` make hallucinations more visible (AI must declare assumptions and note unknowns) — but final verification is always the user's.

**"Why does my field activation not seem to change the output?"**
1. Open a new chat (old context can override)
2. Raise the weight: `activate linus=0.9` (not 0.3)
3. Run `tools/fingerprint.py` on before/after — distance > 0.3 confirms it fired. If the shift is real but subtle, the expectation was too high.

**"Is there commercial support?"**
Aether Pro · `docs/contact.md` for buying flow. WeChat `wsl497810` for direct contact.

---

## What this repo is NOT

- **NOT a SaaS** — no server, no login, no cloud.
- **NOT an LLM** — bring your own Cursor / Claude / GPT key.
- **NOT a prompt framework** — prompts are commands; fields are weighted dimensions. Different abstraction.
- **NOT a complete Aether** — full workspace (species, memory layer, self-evolution) lives in the maintainer's private repo. This kit ships what's production-ready for daily individual use.

---

## Version

Aether Kit v0.4.1 · released 2026-04-18

See `templates/aether.mdc.template` for the activation protocol that ships with every install.

For the full story of how Aether was built(Day 1-30 public experiment), see the live site: http://82.156.228.168/

---

*Maintainer: [@497810wsl](https://github.com/497810wsl) · WeChat `wsl497810`*
