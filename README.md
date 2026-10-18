# gyanano-skills

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Skills](https://img.shields.io/badge/skills-2-blue.svg)](#技能)
[![Format: Agent Skills](https://img.shields.io/badge/format-Agent%20Skills-6f42c1.svg)](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
[![Python 3](https://img.shields.io/badge/python-3.x-3776AB.svg)](controlled-chinese/scripts/zh-lint.py)

简体中文 · [English](README.en.md)

一组 [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)，由 [@gyanano](https://github.com/gyanano) 维护。

每个技能是一个自包含目录，内含一份带 YAML frontmatter（`name`、`description`）的 `SKILL.md`。可选的支撑材料 —— `references/`、`scripts/`、`examples/` —— 按需加载。

## 技能

### [`adaptive-builder-core`](adaptive-builder-core/SKILL.md)

AI 辅助项目执行的三个原则：

1. **Boil the Ocean** —— 把已经落在范围内的活做完。
2. **Search Before Building** —— 先弄清已有的解法，再造新的。
3. **Expertise-Calibrated Agency** —— 按用户**在当前领域**的专业程度调整助手的主动性。

适用于工程、产品、研究或不熟悉的领域：助手要在完整度、复用已有知识、自主性之间取得平衡。三档模式、决策与提问政策的完整说明见 [`adaptive-builder-core/README.md`](adaptive-builder-core/README.md)。

### [`controlled-chinese`](controlled-chinese/SKILL.md)

中文受控语言技能：改写那些**必须被照着执行、而读者问不到作者**的文本 —— 制度、SOP、通知、合同与规则条款、工单、报错、工具描述、agent 指令、需求文档。

中文出事的地方，正是英语不出事的地方，所以它针对的是 ASD-STE100 没有规则可治的机制：零指代（「已完成，请查收。」—— 谁做的，谁收）、意合（分句靠逗号连起来，逻辑关系不写出来）、空词（尽快、适当、必要时、相关部门）、边界未标（「3 日以上」含不含第 3 天，节假日算不算）。三层规则对应这四件事：

1. **指代与逻辑** —— 主语落到纸面上，连接词写出来，一句一动作，限制句长。
2. **词义锁定** —— 一个义务词、一个禁止词、一套并列词，范围端点与时间单位写明。这一层有一半是有依据的：「和 / 以及 / 或者」「应当 / 必须」「不得 / 禁止」，以及「以上 / 以下 / 以内」含本数，均出自《立法技术规范（试行）（一）》（全国人大常委会法工委，2009）。
3. **情态保护** —— 情态是内容，空词不是。把词删掉，看句子的真假会不会变：会变（可能、大概率、不排除），保留，哪怕因此超出字数上限；不会变（尽快、适当），换成时间、条件或数字。技能不许编数字 —— 定不下来的「尽快」写成 `【待定：…】`，再加一行 `未定：`。

两档：**执行档**（三层全执行，含硬性上限）和**阅读档**（第一层与第三层，加上第二层里带纠纷代价的那几条）。默认只输出改写后的正文，其后只跟可能存在的 `未定：` 与 `保留原样：` 行。

`scripts/zh-lint.py` 是确定性、仅用标准库的 linter，带 `--selftest`：查分号串联的动作、半角标点、空时间 / 空条件 / 空数量 / 空主体、虚动词、行话、套话、双重否定、义务词轮换、范围边界未标、时限单位混用、超长句、逗号链、无主状态句、无施事的「被」字句、套叠的「的」链、同义轮换，以及说到一半的列表项。它**永不查情态**。前后对照、安装步骤，以及它故意不查的项目，见 [`controlled-chinese/README.md`](controlled-chinese/README.md)。

## 仓库结构

```
gyanano-skills/
├── README.md            # 简体中文（默认）
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

## 安装技能

把技能目录复制进你的 agent 的 skills 目录：

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

agent 启动时只读 `name` 和 `description`，技能被触发后才加载 `SKILL.md` 的其余部分。支撑文件只在 `SKILL.md` 指过去时才读。

## 许可

MIT —— 见 [LICENSE](LICENSE)。许可覆盖整个仓库，各技能目录不再单独带一份副本。
