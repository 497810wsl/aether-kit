# 🏗️ Architect Recipe

**Use when**: system design, trade-off analysis, writing design docs / RFCs / proposals.

---

## One-line activation

```
activate engineering-rigor=0.8, nolan=0.5, linus-torvalds=0.4, cold-to-warm=-0.1
```

## Install the fields

```bash
aether fetch engineering-rigor
aether fetch nolan
aether fetch linus-torvalds
aether fetch cold-to-warm
```

## What you get

- Every design choice paired with **what it rules out**
- Trade-offs explicitly named, not hidden
- Narrative structure that helps the reader think with you
- Firm rejection of "let's do both" and "we'll decide later"
- Concrete failure modes for each proposed design
- Rollback / decision-reversibility treated as first-class

## Example prompts

```
activate engineering-rigor=0.8, nolan=0.5, linus-torvalds=0.4, cold-to-warm=-0.1

Design a rate limiting system for our API.
Constraints: 100k req/s peak, 99.9% availability, multi-region.
Give me 2–3 options with explicit trade-offs, not a "recommended" one.
```

```
activate engineering-rigor=0.8, nolan=0.5, linus-torvalds=0.4, cold-to-warm=-0.1

Review this design doc draft: [paste]
What's the most important question it doesn't answer?
```

```
activate engineering-rigor=0.8, nolan=0.5, linus-torvalds=0.4, cold-to-warm=-0.1

We're choosing between PostgreSQL with logical replication vs. Debezium CDC
for our event pipeline. Both seem fine. Help me see what makes them different
in the failure cases we haven't thought about yet.
```

## Variants

**For pre-mortem / adversarial review** (break your own design):

```
activate engineering-rigor=1.0, linus-torvalds=0.9, cold-to-warm=-0.4
```

**For collaborative design exploration** (thinking out loud with the AI):

```
activate engineering-rigor=0.7, nolan=0.6, jony-ive=0.3, cold-to-warm=+0.2
```

**For writing up a design doc** (once decisions are made):

```
activate engineering-rigor=0.7, jony-ive=0.6, cold-to-warm=+0.2
```

## Signal it's working

- Options are presented with **what they preclude**, not just what they enable
- Trade-offs are stated upfront, not buried at the end
- Mentions observability, blast radius, and rollback for each option
- Explicit about **reversibility**: "this is a one-way door because..."
- Pushes back on ambiguity: "you haven't specified X, that changes everything"
- Ends with the most important question you haven't asked yet

## Signal it's not working

- Presents one "recommended" option with alternatives as afterthoughts
- Uses "scalable", "robust", "flexible" without defining what those mean here
- No mention of failure modes
- Fails to ask clarifying questions when the problem is under-specified
  → Your `engineering-rigor` field weight might be too low. Try 0.9+.

## Anti-pattern watch

A good architect recipe should make you uncomfortable sometimes. If every output feels like "yes, great idea, let me elaborate" — the recipe is broken.

The rigor field should occasionally respond with:

> "The question as posed has a hidden assumption: you're assuming X is fixed. If we relax X, the answer changes completely. Is X actually fixed, and if so, why?"

If you never get that kind of pushback, bump `engineering-rigor` higher.

---

## Chains well with

- **Debugger** — when an architecture discussion exposes a specific failure to investigate
- **Code Reviewer** — when moving from design to reviewing the implementation
- **Technical Writer** — when writing up the final decision for stakeholders

---

[← all recipes](./) · [report issue](https://github.com/497810wsl/aether/issues)
