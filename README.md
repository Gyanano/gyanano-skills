# gyanano-skills

A collection of [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) maintained by [@gyanano](https://github.com/gyanano).

Each skill is a self-contained directory holding a `SKILL.md` file with YAML frontmatter (`name`, `description`). Optional supporting material — `references/`, `scripts/`, `examples/` — is loaded on demand.

## Skills

### [`adaptive-builder-core`](adaptive-builder-core/SKILL.md)

Three principles for AI-assisted project execution:

1. **Boil the Ocean** — complete the work already in scope.
2. **Search Before Building** — understand existing solutions before inventing new ones.
3. **Expertise-Calibrated Agency** — adjust assistant initiative to the user's expertise in the current domain.

Use it for engineering, product, research, or unfamiliar-domain tasks where the assistant must balance completeness, reuse of existing knowledge, and autonomy.

## Installing a skill

Copy the skill directory into your agent's skills folder:

```
<skills-dir>/
  adaptive-builder-core/
    SKILL.md
```

The agent reads only `name` and `description` at startup, and loads the rest of `SKILL.md` when the skill is triggered.
