# Aether · Federated Memory(Day 10 · coll-0082)

> 从 Day 9 "scope-aware status line"(止血)到 Day 10 "联邦记忆真架构"。
> 目标:Owner 在 novel-project / OpenClaw / 任何 guest 项目中得到**本项目自己的** handover / coll / tasks,同时保留跨项目共享的 Owner 身份 / 5-mode / species。

---

## 1. 三层数据模型

```
┌──────────────────────────────────────────────────────────────┐
│  ~/.aether-core/                    ← USER scope · 全局      │
│    core/                                                      │
│      pact.md                        ← 跨项目身份 / 契约      │
│      fields/**/*.field.md           ← 5-mode + Pro 场工具集  │
│      species-registry.json          ← 进化符号(非 nursery)  │
│    manifest.json                    ← core version + built   │
│  ──────────────────────────────────────────────────────────── │
│  Read by:   aether_handshake · _build_*_briefing core section │
│             aether_query    · identity / fields queries       │
│  Writer:    aether_federate init-core(bootstrap + upgrade)   │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  <project>/.aether/                 ← PROJECT scope · 每项目 │
│    handover/                                                  │
│      day-*-handover.md              ← 本项目独立 Day 计数     │
│    coll/                                                      │
│      coll-*.md                      ← 本项目坍缩(编号独立)  │
│    tasks.jsonl                      ← 本项目任务账本          │
│    events.jsonl                     ← 原有 · coll-0072 写侧   │
│    transcripts/*.txt                ← 原有 · snapshot         │
│    agent-responses/*.md             ← 原有 · 决策型           │
│    manifest.json                    ← scope / init_at /        │
│                                       linked_core_version     │
│    index.db(Day 11+)                ← per-project B-layer     │
│  ──────────────────────────────────────────────────────────── │
│  Read by:   aether_handshake · _build_guest_briefing overlay  │
│             aether_tasks(当 cwd ∈ project)                  │
│             aether_daily(当 cwd ∈ project)                  │
│  Writer:    aether_project init(bootstrap)                   │
│             aether_hook · 写事件(coll-0072 管道)             │
│             aether_tasks · add/close(已有)                  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  <central-skills>/aether/           ← CENTRAL · Aether 自己  │
│    gen4-morphogen/fields/           ← 源 fields(core 从这拷)│
│    gen5-ecoware/species-registry    ← 源 species             │
│    gen6-noesis/collapse-events/     ← Aether-dev 专属 coll   │
│    docs/daily/day-*-handover.md     ← Aether-dev 自身 handover│
│    labs/chronicle/collaboration-pact.md  ← 源 pact(core 从此)│
│  ──────────────────────────────────────────────────────────── │
│  Role:      skills workspace 本身降格为"第一个 overlay"       │
│             · 中央 docs/daily + gen6-noesis 是**它自己**的    │
│               overlay 数据 · 不是全局共享                      │
│             · 但源文件(gen4/gen5/labs/chronicle)仍是 core   │
│               的权威来源 · init-core / upgrade 从这里复制     │
└──────────────────────────────────────────────────────────────┘
```

**口诀**:

- `core` = **Owner 的人格 + 工具库** · 跨项目永远适用 · 不包含"Owner 今天做了什么"
- `overlay` = **本项目的工作日志 + 任务** · 只在该项目上下文中有意义
- `central` = Aether **源代码 + 自己的 overlay** · 不做跨项目共享(除非被 init-core 拷出)

---

## 2. 迁移 / 装机顺序

新手 Owner(或新设备)第一次用 Aether 的路径:

```
Step 1: clone / download aether · 放到任意目录(成为 central skills)
Step 2: cd <central-skills>
Step 3: python aether/bin/aether_install.py --global --apply
        · 装 ~/.cursor/hooks.json(hooks)
        · 装 ~/.cursor/rules/aether.mdc(rules)
        · 装 %LOCALAPPDATA%/Microsoft/WindowsApps/aether.bat(CLI)
Step 4: aether federate init-core        ← Day 10 新增
        · 从 central 拷 pact + 9 fields + species 到 ~/.aether-core/
        · 写 ~/.aether-core/manifest.json
Step 5: (可选)在任意 guest 项目:
        cd D:\some-project
        aether project init              ← Day 10 新增
        · 创建 .aether/{handover,coll,tasks.jsonl,manifest.json}
        · 打开 Cursor 后 guest briefing 就能渲染本项目记忆
```

老手 Owner(已装 · Day 8 → Day 10)的平滑升级:

```
Step 1: git pull(已在 central 仓内)
Step 2: aether federate init-core        ← 幂等 · 已有 core 则只 upgrade
Step 3: (可选)老的 guest 项目:aether project init
```

`init-core` 必须**幂等**:重复跑不破坏,版本比对,needs_upgrade 时才覆盖文件。

---

## 3. 兼容性契约

### 3.1 向后兼容(Day 1-9 老代码不改坏)

- `aether_events.resolve_data_dir(payload)` 保留签名 · 内部委托给 `resolve_overlay_dir(payload)` · 老调用仍返回同样路径
- `aether_handshake.build_briefing(payload)` 已 Day 9 完成 · Day 10 只扩展 `_build_guest_briefing` 内容 · 不改签名
- `aether_tasks.py` / `aether_daily.py` / `aether_doctor.py` 的 `DATA_DIR = WORKSPACE_ROOT / ".aether"` 继续工作(当在 central 仓跑时 · DATA_DIR = central/.aether 等同于 central 的 overlay)

### 3.2 前向兼容(Day 11+ 扩展不破 Day 10)

- `~/.aether-core/manifest.json` 的 `core_version` 字段递增 · upgrade 路径用 version-aware migrate
- overlay `.aether/manifest.json` 的 `linked_core_version` 记录兼容的 core · 不兼容时 `aether project doctor` 报警

### 3.3 central = 降格 overlay 的语义等价

- 当 `cwd = central-skills` · overlay dir = `central-skills/.aether/`(已有)· `central-skills/aether/docs/daily/` 是"central 自己的 handover"(不是 overlay)
- Day 9 handshake 已区分这两个 · Day 10 **不强制迁移** central 的 handover 到 `.aether/handover/` · 保持 `docs/daily/` 兼容(`latest_handover()` 在 dev-self 仍读 `docs/daily/`)
- **原因**:Aether 自己的源代码仓里的历史数据(71 个 coll · 9 个 handover)是 git 管控的 · 移动会破坏 git history · 价值 < 风险 · 留原位

---

## 4. 路径 resolve 总规

### 4.1 `aether_events.resolve_core_dir() -> Path`

```python
Path.home() / ".aether-core"
```

无 fallback · 未 init 返回不存在的路径 · 调用方 `if core_dir.exists()` 自行判断。

### 4.2 `aether_events.resolve_overlay_dir(payload=None) -> Path`

```python
if payload.workspace_roots[0]: return <root>/.aether
elif env AETHER_DATA_DIR:      return <env>
else:                           return cwd/.aether  # CLI 路径 · 取 cwd
```

**变化**:Day 9 `resolve_data_dir` 的 fallback 是 `WORKSPACE_ROOT/.aether`(central 的)· 这会让 CLI 在 guest 项目跑时仍然写到 central。Day 10 改成 `cwd/.aether`(或保留 `WORKSPACE_ROOT/.aether` 兼容 CLI 在其他文件夹误跑的情况 · 这里选**保留 Day 9 行为** · 只在显式 `payload` / env 时切换)。

**决策**:**保持 Day 9 fallback(WORKSPACE_ROOT)不变** · 否则 `aether tasks add` 在 C:\Windows\System32 误跑会创建垃圾目录。新语义只通过 payload / env 显式激活。

### 4.3 `aether_handshake._build_guest_briefing(ws_root)`

```
pact section:
  先尝试 core_dir/core/pact.md
  fallback 到 central/labs/chronicle/collaboration-pact-2026-04-17.md
  · 防止用户没跑 init-core · 仍然有身份注入

project overlay section:
  读 ws_root/.aether/handover/day-*-handover.md(最新一个)
  读 ws_root/.aether/coll/coll-*.md(最近 3 个 semantic)
  读 ws_root/.aether/tasks.jsonl(open P0 only)
  · 任一缺失 · 不渲染该 sub-section · 不报错
```

---

## 5. 不做 / 反模式

- ❌ **不把 central 的 gen6-noesis / docs/daily 拷进 core**:它们是 Aether-dev 的 overlay 数据 · 放进 core 意味着"所有用户的 guest 项目都能看 Owner 开发 Aether 的 8 天日记"· 严重隐私泄漏
- ❌ **不自动 init-core 在 `--global --apply` 时**:Owner 需要显式意图 · 避免意外写 home 目录
- ❌ **不把 overlay 的 coll 跨项目合并**:每个项目自包含 · 想跨项目检索用未来的 `aether query --all-overlays`(Day 12+)
- ❌ **不做 cloud sync · 不做 multi-device**:Day 10 本地 only · git / OneDrive 手工 sync · Day 30+ 评估

---

## 6. 验收标准(Day 10 P0 Done 的定义)

1. ✅ `aether federate init-core` 幂等跑出 `~/.aether-core/core/{pact.md, fields/, species-registry.json}` + `manifest.json`
2. ✅ `aether federate status` 报告 core 存在 + version
3. ✅ `aether project init` 在 cwd 创建 `.aether/{handover,coll}` + `tasks.jsonl` + `manifest.json` · 幂等 · 不覆盖已有内容
4. ✅ `aether project status` 报告 overlay 健康(handover count · coll count · open tasks)
5. ✅ guest briefing 在有 overlay 的项目真渲染本地 handover / coll / open P0
6. ✅ guest briefing 在无 overlay 的项目仍显示 "init 提示"(Day 9 行为)
7. ✅ dev-self briefing(cwd = central)不回归 · 完整 3700 字符 · Day 1-9 工作流不坏
8. ✅ selfcheck 100/100 · 0 lint
9. ✅ coll-0082 归档 + task-0029 close

---

## 7. 和未来 trend 的关系(for Day 15 launch narrative)

| 趋势 | Aether 联邦记忆的对位 |
|---|---|
| Claude Skills(SKILL.md · progressive disclosure) | `~/.aether-core/core/fields/*.field.md` 和 SKILL.md 同构 · Day 11 P2 的 export 适配 |
| Cursor Global Rules(~/.cursor/rules) | `~/.aether-core/core/` 与 `~/.cursor/rules/aether.mdc` 相邻 · 职责分离:rules 是"规则" · core 是"记忆库" |
| Letta / MemGPT 分层记忆 | core = memory_blocks(identity · pact)· overlay = episodic(per-project) · 映射干净 |
| Obsidian vault | central = vault · core = template · overlay = per-project notes · 直接可迁移 |
| MCP servers | Day 10 P1 wrap: `aether_remember/query/forget` 跨 core + overlay 查 · 对外暴露统一 tool |

Aether 的**护城河 = core + overlay 同时由一套 reflex arc(10 hooks)驱动** · 不是多独立工具拼装。

---

_coll-0082 讲实施 · 本文讲设计意图 · 两者互补_
