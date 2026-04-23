<div align="center">

# ⟁ Aether

### Cursor 跨会话记忆

**你的 Cursor 每次新 chat 都会"失忆"· Aether 不会。**

[![License: PolyForm NC 1.0.0](https://img.shields.io/badge/License-PolyForm_NC_1.0.0-yellow.svg)](https://github.com/497810wsl/aether-kit/blob/main/LICENSE)
[![Works with](https://img.shields.io/badge/适配-Cursor-brightgreen.svg)](https://cursor.com)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)]()
[![Install: 5 min](https://img.shields.io/badge/安装-5_分钟-ff69b4.svg)](#安装)

**[安装](#安装) · [它做什么](#它做什么) · [诚实现状](#诚实现状) · [English](./README.en.md)**

</div>

---

## 它做什么

Cursor 每次开新 chat · AI 都是白板状态。你昨天做了 30 个架构决定 · 今天的 chat 一无所知。你前 10 分钟在复制粘贴上下文 · 或者懒得复制 · AI 开始建议你昨天刚否决的方案。

Aether 解决这个。新 chat 开起来的瞬间 · `sessionStart` hook 自动跑 · 读你最近一份 handover + 最近 3 条决策日志(collapse)+ 你的 pact 文件 + 5-mode 激活规则 · 打包注入到 AI 的 `additional_context`。**AI 第一条回复就已经知道你昨天到哪儿了**。

就这一件事。**1 个能力 · 0 账号 · 0 云端**。数据永远不离开你的机器。

---

## 诚实现状

在你往下看之前 · 先看**今天的真数据**:

| 指标 | 数值 | 含义 |
|---|---|---|
| GitHub stars | **0** | 作者之外 · 没人验证过 |
| 付费用户 | **0** | 暂无付费档 |
| 项目年龄 | ~12 天 | 作者 solo · 公开开发 · 从 0 到现在 |
| 生产用户 | **1**(作者自己) | n=1 · 每天用 |
| 外部贡献者 | **0** | PR 欢迎 |

如果这让你不安 · 30 天后回来看。如果你 OK · 继续往下。

---

## 给谁用

**适合你 · 如果**:

- 你每天都用 Cursor / Claude Code · 做**同一个项目**(或几个长期项目)
- 你不止一次撞到 "开新 chat 要重新解释上下文" 的墙
- 你能接受"每次新 IDE session 跑一次 Python 脚本"
- 你想看一个 dev tool 公开演化 · 不要营销包装

**不适合你 · 如果**:

- 你临时用 Cursor · 项目碎片化
- 你要团队协作工具(这是单人工具)
- 你要 GUI / 网页控制台(Aether 只有 CLI + IDE hooks)
- 你期望今天就给你 v1.0 抛光版 —— 这是公开开发第 2 周的作品

---

## Aether 给你什么

| 能力 | 今天可用 | 做什么 |
|---|---|---|
| **Session handshake** | ✅ | 新 chat 读你最近 handover + 最近 3 条决策 · AI 第一条就有上下文 |
| **9 种 IDE hook** | ✅ | `sessionStart` / `stop` / `postToolUse` 等 · 每个有意义事件写 `.aether/events.jsonl` |
| **项目级隔离** | ✅(Day 12)| 项目 A 的记忆不泄漏到项目 B · 每个项目自己的 `.aether/` overlay |
| **5-mode 自动激活** | ✅ | 说"review this code" → AI 自动切 code-review 人格 · 无需前缀 |
| **语言匹配** | ✅(Day 12)| 你说中文 → AI 回中文 · 你说英文 → 英文 · 不绕 |
| **诚实自检** | ✅ | `aether selfcheck --honest` 不只看"文件在不在" · 还看"外部用户有没有" |
| **npm 包** | 🚧 | 计划中 · 今天靠 `git clone` 装 |
| **团队同步** | ❌ | 设计上就是单人 |

---

## 安装

需要 Python 3.9+ 和 Cursor。

### 1. 克隆

```bash
git clone https://github.com/497810wsl/aether-kit ~/aether
```

### 2. 全局安装(任何 Cursor session 都自动用)

```bash
cd ~/aether
python aether/bin/aether_install.py --global --apply
```

会写 `~/.cursor/hooks.json` + `~/.cursor/rules/aether.mdc`。你已有的 Cursor 配置会 `.bak` 备份再覆盖。

### 3. 重启 Cursor · 打开任意项目 · 新 chat · 输入 `你好`

AI 第一行**必须**是类似这样:

```
⟁ Aether · Day 12/30 · 86/100 (32 ok · 2 warn · 3 fail) · scope: dev-self · handover: day-11-handover.md
```

(如果是没注册过的项目 · 会看到 `unregistered` 替代 `Day N/30` · 跑 `aether project init --apply` 注册。)

看到这行 · Aether 就在跑。看不到 · 查 [故障排查](./docs/USING-IN-OTHER-PROJECTS.md#5--排错)。

### 4.(可选)给某个项目独立注册

在项目根目录:

```bash
aether project init --apply
```

创建 `.aether/` · 给该项目独立的 handover 日志 / Day 计数 / task ledger。**可逆** · 随时 `aether project uninstall --apply` 卸掉。

---

## 你会看到什么

**已注册项目 · 新 chat**,AI 回复开头:

```
⟁ Aether · Day 3/30 · ?/? · scope: guest @ my-project · handover: day-2-handover.md
```

- `Day 3/30` = 你在这个项目用 Aether 工作的第 3 天
- `scope: guest @ my-project` = 你在 `my-project` · 不是 Aether 自己的开发仓
- `handover: day-2-handover.md` = AI 已读 day-2 handover · 知道你昨天在干啥

之后正常对话。AI **不会再问**"我们上次到哪儿了?"· 因为它已经知道。

**当日结束**,一条命令写明天的入口:

```bash
aether daily write
```

生成 `day-N-handover.md` · 下次 chat 读它。**记忆连续。**

---

## Aether **不是**什么

- ❌ **不替代 Cursor** · 它作为 hooks + rules 挂在 Cursor 上
- ❌ **不是更好的 LLM** · 同一个 AI · 同样的 output 质量 · 只是多了**记忆**
- ❌ **不是 prompt 库** · 它不改你的 prompt · 它给 AI 会话级上下文
- ❌ **不是 "带权重的 field 框架"**(早期 Aether 是这个定位 · 形态 α 把它从头条移走 · field 仍在 · 只是不当主卖点)
- ❌ **不是颠覆者** · 12 天大 · 1 个作者 · 0 外部验证。作者自己的 reality-check 见 [scope reaffirmation](https://github.com/497810wsl/aether-kit/blob/main/labs/chronicle/scope-reaffirmation-2026-04-22.md)

---

## FAQ

<details>
<summary><b>Cursor 会不会把这功能内置 · 让 Aether 过时?</b></summary>

可能。Cursor Desktop 已经有部分 memory 功能。如果他们原生 ship 完整的 session handshake · Aether 核心价值会缩水。这个风险真实 · 写在 [WHY-NOT.md](./docs/WHY-NOT.md) 里。作者的赌注:有 6-18 个月窗口期 · Aether 做这件事比 Cursor 下个版本好 · 这个窗口值得下注 · 即便它会关。

</details>

<details>
<summary><b>你会存我的代码 / prompt 到哪儿吗?</b></summary>

不存。零云端 · 零 telemetry · 零账号。`.aether/events.jsonl` 在你磁盘 · handover 文件在你磁盘 · collapse 日志在你磁盘。任何文本编辑器都能查。`aether project uninstall --apply` 一键清。

</details>

<details>
<summary><b>"handover" / "collapse" / "dev-self" 是啥 · 是邪教术语吗?</b></summary>

只是命名 · 不是教条。**handover** = 给明天的你的备忘 · **collapse** = 一次重要决策的日志 · **dev-self** = 你在开发 Aether 本身 vs 用 Aether 在别的项目。词可以换 · 我们留着因为改会破坏老用户肌肉记忆。你讨厌这些词 · `grep -r "collapse" .` 批量重命名 · 完全可以。

</details>

<details>
<summary><b>我能不用"30 天实验" / "pact" 这套叙事吗?</b></summary>

能。30 天叙事是**作者对自己**的承诺 · 不是对你的。删 `labs/chronicle/collaboration-pact-2026-04-17.md` · 其他功能照跑。status line 在刚注册的项目从 "Day 1" 开始 · 随你写 handover 推进。

</details>

<details>
<summary><b>为啥 Python 3.9+ ?</b></summary>

walrus operator · type hints · `pathlib`。**0 外部依赖** · 纯 stdlib。你有 Cursor · 大概率有 Python。没有的话:`brew install python@3.11` / `winget install Python.Python.3.11` · 完事。

</details>

<details>
<summary><b>Windows / Linux / Mac 都行吗?</b></summary>

都行。作者每天在 Windows 上跑。PowerShell 路径处理到位 · LF/CRLF 基本 handled。你平台出问题 · 开 issue。

</details>

---

## 反馈 · 请

如果你装了这个 · 有**任何**反应 —— "有用" / "噪声" / "hero 那行没看懂" / "第二天挂了" —— 开 GitHub issue。**1 个 star 是公开验证 · 1 条 "这没用" 比沉默安装更值钱**。

**作者公开承诺的 Day 30 成功标准**(今天 Day 12):

- 1 个不认识作者的 dev star 这个 repo → **赢** · 继续做到 Day 30+
- 5 个被作者手动邀请的 dev 试用 → **赢** · 同样
- 30 天过 · 0 外部用户 → **归档** · 经验写成方法论文章公开

---

## 联系

- **微信**:`wsl497810`(首条消息请提"Aether")
- **GitHub Issues**:<https://github.com/497810wsl/aether-kit/issues>
- **Discussions**:<https://github.com/497810wsl/aether-kit/discussions>

---

## 许可

[**PolyForm Noncommercial 1.0.0**](./LICENSE) © 2026 · [@497810wsl](https://github.com/497810wsl)

- ✅ **允许** · 个人 / 研究 / 业余 / 非营利组织使用 · 修改 · 分发(须保留 `Required Notice` 行)
- ❌ **禁止** · 商业使用(含公司内部)
- 🏢 **商业许可** · 微信 `wsl497810` 洽谈

**为什么不是 MIT**:Aether 是作者单人项目 · 想保证"被用但不被白嫖进商业产品"。非商用场景完全自由 · 商用必须联系作者。

---

<div align="center">

*Cursor 跨会话记忆 · 你的 AI 不再失忆 · 就这。*

⟁

</div>
