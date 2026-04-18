# ✍️ Technical Writer Recipe

**Use when**: writing docs, READMEs, API reference, tutorials, blog posts about tech.

---

## One-line activation

```
activate jony-ive=0.7, engineering-rigor=0.5, cold-to-warm=+0.3
```

## Install the fields

```bash
aether fetch jony-ive
aether fetch engineering-rigor
aether fetch cold-to-warm
```

## What you get

- Restrained, textured prose (not feature soup)
- Central tension stated early (e.g., "a cache is a promise you make to yourself")
- One metaphor held steadily, not five chaotic ones
- Warm-enough to be human, disciplined enough to be accurate
- Ruthless deletion of filler ("best practices", "optimal", "leverage")

## Example prompts

```
activate jony-ive=0.7, engineering-rigor=0.5, cold-to-warm=+0.3

Write a one-paragraph intro for a docs page about our caching system.
Make it compelling but honest.
```

```
activate jony-ive=0.7, engineering-rigor=0.5, cold-to-warm=+0.3

Draft a README hero for this library: [describe library]
Avoid marketing speak. One clear value proposition.
```

```
activate jony-ive=0.7, engineering-rigor=0.5, cold-to-warm=+0.3

Explain promise-based async to someone who only knows callbacks.
Two paragraphs max.
```

## Variants

**Pure style, no engineering discipline** (for marketing pages, landing content):

```
activate jony-ive=0.8, cold-to-warm=+0.5
```

**Nolan-inspired long-form** (for deep explainers, essays):

```
activate nolan=0.7, jony-ive=0.4, engineering-rigor=0.5, cold-to-warm=+0.2
```

**Punchy / opinionated** (blog posts, essays with a point of view):

```
activate linus-torvalds=0.5, jony-ive=0.5, cold-to-warm=0
```

## Signal it's working

- First sentence gives you a reason to read the second
- Uses concrete nouns and verbs, not adjectives ("promise" not "wonderful")
- Max 1 metaphor per paragraph, held consistently
- Technical claims are specific and verifiable
- Ends with what the reader will learn / do, not "we hope you enjoyed"

## Signal it's not working

- Opens with "In this guide, we will..."
- Uses "leverage", "optimal", "best practices", "seamlessly"
- Multiple unrelated metaphors competing
- Features listed in sequence with no through-line
  → The `jony-ive` field probably didn't fire. Check your `.aether/fields/`.

## Good vs. bad output

**Without Aether**:
> "Our caching system is designed to improve application performance by storing frequently accessed data in memory. By reducing database queries and computation time, caching provides faster response times and a better user experience."

**With this recipe**:
> "A cache is a promise you make to yourself: this data won't change for the next 60 seconds, so I won't ask again. Keep that promise and responses get faster. Break it and users see stale data, which is often worse than slow data."

Same topic. The second has a point of view.

---

[← all recipes](./) · [report issue](https://github.com/497810wsl/aether/issues)
