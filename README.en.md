# gyanano-skills

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/skills-2-blue.svg)](#skills)
[![Format: Agent Skills](https://img.shields.io/badge/format-Agent%20Skills-6f42c1.svg)](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
[![Python 3](https://img.shields.io/badge/python-3.x-3776AB.svg)](controlled-chinese/scripts/zh-lint.py)

English · [简体中文](README.md)

A collection of [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) maintained by [@gyanano](https://github.com/gyanano).

Each skill is a self-contained directory holding a `SKILL.md` file with YAML frontmatter (`name`, `description`). Optional supporting material — `references/`, `scripts/`, `examples/` — is loaded on demand.

## Skills

### [`adaptive-builder-core`](adaptive-builder-core/SKILL.md)

Three principles for AI-assisted project execution:

1. **Boil the Ocean** — complete the work already in scope.
2. **Search Before Building** — understand existing solutions before inventing new ones.
3. **Expertise-Calibrated Agency** — adjust assistant initiative to the user's expertise in the current domain.

Use it for engineering, product, research, or unfamiliar-domain tasks where the assistant must balance completeness, reuse of existing knowledge, and autonomy. [`adaptive-builder-core/README.md`](adaptive-builder-core/README.md) covers the three expertise modes and the decision and question policy in full.

### [`controlled-chinese`](controlled-chinese/SKILL.md)

A Chinese controlled-language skill: rewrite text that someone must **execute** and cannot ask the author about — policies, SOPs, notices, contract and rule clauses, tickets, error messages, tool descriptions, agent instructions, requirement docs.

Chinese goes ambiguous where English does not, so the skill targets the mechanisms ASD-STE100 has no rules for: zero anaphora (「已完成，请查收。」 — who did it, who receives it), parataxis (clauses joined by a comma with the logical relation left unwritten), content-free words (尽快, 适当, 必要时, 相关部门), and unstated boundaries (does 「3 日以上」 include day 3, do holidays count). Three layers address them:

1. **Reference and logic** — put subjects on the page, write the connective out, one action per sentence, sentence-length caps.
2. **Vocabulary locking** — one obligation word, one prohibition word, one conjunction set, explicit range endpoints and time units. Half of this is normative: 「和 / 以及 / 或者」, 「应当 / 必须」, 「不得 / 禁止」, and 「以上 / 以下 / 以内」含本数 come from 《立法技术规范（试行）（一）》(全国人大常委会法工委, 2009).
3. **Modality protection** — modality is content, empty words are not. Delete the word and ask whether the sentence's truth changes: if it does (可能, 大概率, 不排除), keep it even past the length cap; if it does not (尽快, 适当), replace it with a time, a condition, or a number. The skill never invents numbers — an unresolvable 「尽快」 becomes `【待定：…】` plus a `未定：` line.

Two modes: **execution** (all three layers, hard limits) and **reading** (layers 1 and 3, plus the second-layer rules that carry dispute cost). Default output is the rewritten text alone, followed only by any `未定：` and `保留原样：` lines.

`scripts/zh-lint.py` is a deterministic, stdlib-only linter with `--selftest`: it flags semicolon-chained actions, half-width punctuation, empty time / condition / quantity / subject words, empty verbs, jargon, boilerplate, double negation, obligation-word rotation, unstated range boundaries, mixed time units, over-long sentences, comma chains, subjectless status sentences, agentless 「被」 sentences, stacked 「的」 chains, synonym rotation, and list items that stop mid-thought. It never flags modality. [`controlled-chinese/README.md`](controlled-chinese/README.md) has before/after pairs, install steps, and the checks the linter deliberately does not perform.

## Repository layout

```
gyanano-skills/
├── README.md            # Simplified Chinese (default)
├── README.en.md         # English
├── LICENSE
├── adaptive-builder-core/
│   ├── SKILL.md
│   └── README.md
└── controlled-chinese/
    ├── SKILL.md
    ├── README.md
    ├── references/
    │   ├── rules.md
    │   └── lexicon.md
    ├── examples/
    │   ├── before-after.md
    │   └── linter-edge-cases.md
    └── scripts/
        └── zh-lint.py
```

## Installing a skill

Copy the skill directory into your agent's skills folder:

```
<skills-dir>/
  adaptive-builder-core/
    SKILL.md
    README.md
  controlled-chinese/
    SKILL.md
    README.md
    references/
    scripts/
    examples/
```

The agent reads only `name` and `description` at startup, and loads the rest of `SKILL.md` when the skill is triggered. Supporting files are read only when `SKILL.md` points to them.

## License

MIT — see [LICENSE](LICENSE). The license covers the whole repository, so no skill directory carries its own copy.
