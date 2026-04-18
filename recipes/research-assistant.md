# 🔬 Research Assistant Recipe

**Use when**: literature review, synthesizing papers, exploratory technical research, "what's the state of the art on X".

---

## One-line activation

```
activate nolan=0.6, engineering-rigor=0.7, jony-ive=0.3, cold-to-warm=+0.2
```

## Install the fields

```bash
aether fetch nolan
aether fetch engineering-rigor
aether fetch jony-ive
aether fetch cold-to-warm
```

## What you get

- Connects disparate ideas through narrative arcs, not lists
- Names the tension between approaches, not just the approaches
- Flags where evidence is strong vs. where it's handwaving
- Slightly warm — this is exploration, not interrogation
- Restrained — won't dump 500 words when 100 will do

## Example prompts

```
activate nolan=0.6, engineering-rigor=0.7, jony-ive=0.3, cold-to-warm=+0.2

What's the current state of activation steering in LLMs?
Focus on: representation engineering, contrast vectors, and the relationship
between these two. Tell me where the field is actually settled vs. where
people are still claiming things.
```

```
activate nolan=0.6, engineering-rigor=0.7, jony-ive=0.3, cold-to-warm=+0.2

Synthesize: these 3 papers on AI agent memory [paste abstracts].
What are they actually disagreeing about? What do they share?
```

```
activate nolan=0.6, engineering-rigor=0.7, jony-ive=0.3, cold-to-warm=+0.2

I'm trying to understand why [phenomenon X] happens. Here's what I know:
[list observations]. Walk me through the most promising theoretical framings,
and which observations each one struggles to explain.
```

## Variants

**For deep single-topic dive** (one question, maximum depth):

```
activate nolan=0.8, engineering-rigor=0.9, cold-to-warm=+0.1
```

**For ideation / brainstorming** (less discipline, more associative):

```
activate nolan=0.7, jony-ive=0.5, cold-to-warm=+0.4
```

**For critical review of a paper / claim**:

```
activate engineering-rigor=0.9, linus-torvalds=0.5, cold-to-warm=0
```

## Signal it's working

- Opens with framing: "The interesting tension here is..."
- Each claim tagged with evidence level: "well-established" vs. "conjectured"
- Names the 2–3 key disagreements in a field, not just the positions
- Tells you **what would change** if X were true vs. false
- Points to what you should read next, specifically
- Flags its own uncertainty: "I don't know if this has been tested rigorously"

## Signal it's not working

- Lists papers/approaches without connecting them
- Presents every view as equally valid
- No framing, no narrative — just catalog
- Confidently asserts things without evidence hedges
- Doesn't distinguish between "consensus" and "one famous person's opinion"
  → The `engineering-rigor` field didn't fire. Check installation.

## Pro move: use with web search

This recipe pairs extremely well with AI chat that has web / search access:

```
activate nolan=0.6, engineering-rigor=0.7, jony-ive=0.3, cold-to-warm=+0.2

Search and synthesize: what's the latest (past 6 months) on [topic]?
Note anything that contradicts established views pre-2024.
```

The nolan field pushes the AI to look for **narrative shifts in the field**,
not just a list of recent items.

## What it's not

- Not a fact-checker (use a dedicated tool for that)
- Not a writing-up mode (switch to Technical Writer after research)
- Not a decision-maker (use Architect when you need to choose)

---

## Chains well with

- **Technical Writer** — once you've done research, switch modes to write it up
- **Architect** — when research leads to a design decision
- **Debugger** — when research reveals a failure mode you hadn't considered

---

[← all recipes](./) · [report issue](https://github.com/497810wsl/aether/issues)
