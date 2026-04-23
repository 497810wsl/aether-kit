# Aether Path Resolution Spec · v1

> 本文是**工程规范** · 不是哲学叙事。
> 每个 CLI 用哪个路径 resolver · 答错即 bug。
> 变更需 PR · 不得口头约定。

---

## §0 · 本文档的目的

Aether 代码里"`.aether` 是哪个目录" 出过 3 次 bug:

| Day | 问题 | coll |
|---|---|---|
| Day 9 | `build_briefing()` 读 central 但 events 写 per-project · 读写不对称 | coll-0081 |
| Day 11 | `aether tasks add` 写死 central · 用户在 guest 项目加的任务污染开发仓 | coll-0083 |
| Day 13(即将) | `indexer / guardian / autopilot / summarizer / query` 未接通 overlay · B-layer 对 guest 永远失效 | **本文** |

每次都是"某个 .py 文件把 `WORKSPACE_ROOT/.aether` 硬编码了"。
根因:**没有统一规范说明"什么情况用什么 resolver"** · 每个作者凭直觉。

本规范终结这个问题 · 规定:

- 3 类 scope 的精确定义
- 4 个路径 resolver 的职责分工
- 每个 .py 文件的归属类别登记表
- 接口契约 · 错误处理 · 向后兼容承诺

---

## §1 · Scope 模型

Aether 运行时存在**且只存在**以下 3 类 scope,由**运行位置**决定:

### 1.1 `central` scope

```
当前进程的 cwd(或 hook payload.workspace_roots[0])= 中央 skills 仓根
→ 即 WORKSPACE_ROOT(aether_paths.CENTRAL_ROOT)
```

- 数据位置:`<central>/.aether/`
- 代表场景:Owner 在开发 Aether 本身 · 跑 selfcheck / critic / snapshot

### 1.2 `guest` scope

```
当前 cwd 在某个项目根 · 该项目根不是 central · 且项目根下存在 .aether/ 目录
```

- 数据位置:`<project>/.aether/`
- 代表场景:Owner 在 novel-project 里用 Aether(已跑过 `aether project init --apply`)

### 1.3 `core` scope(不是 per-invocation · 是全局共享)

```
~/.aether-core/core/
```

- 数据位置:`Path.home() / ".aether-core" / "core"`
- 代表场景:跨项目共享的身份文件(pact / fields / species)
- **Core 不是"某次调用的 scope"** · 它是所有 scope 的 *supporting data*,由 `aether_federate` 维护

### 1.4 Scope 边界规则

1. `central` 和 `guest` 在任一时刻**只能是一个**(由 cwd / payload 决定)
2. `core` 始终可用(若已 init)· 是 `central` 和 `guest` 共同的 **identity fallback**
3. CLI 没找到任何 overlay(既不在 central 也不在 guest 项目里)→ fallback `central` · 但**打印 stderr 警告** · 不静默写未知位置

---

## §2 · 路径 Resolver · 4 个职责不同的函数

所有 resolver 住在 `aether/bin/aether_paths.py` · **不得在其他文件重新定义**。

### 2.1 `resolve_core_dir() -> Path`

- 输入:无
- 返回:`~/.aether-core/core/`
- 副作用:无
- 失败模式:目录不存在时仍返回路径 · 调用方 `if p.exists()` 判断

### 2.2 `resolve_overlay_dir(payload: dict | None) -> Path`

**hook 专用** · 因为 hook 有 Cursor 给的 `workspace_roots`,不该靠 cwd(hook 的 cwd 可能是 IDE 工作目录)。

- 输入:Cursor hook payload(含 `workspace_roots` 时用其 [0])
- 返回:payload.workspace_roots[0]/.aether · 或 env AETHER_DATA_DIR · 或 `central/.aether`
- 副作用:无
- **只有 `aether_hook.py` 及其依赖(`aether_events.py`)可以调这个**

### 2.3 `resolve_active_overlay(explicit_path, cwd) -> tuple[Path, str]`

**CLI 专用** · CLI 没有 payload · 靠 `--path` / env / cwd 上溯查找。

- 输入:`explicit_path`(来自 `--path` flag)· `cwd`(默认 os.getcwd)
- 返回:`(overlay_dir, source_label)` · source_label ∈ {"explicit", "env", "discovered", "central"}
- 副作用:无
- **所有"写 overlay 数据"的 CLI 必须调这个 · 见 §5 登记表**

### 2.4 `activate_overlay_for_cli(args, announce=True) -> tuple[Path, str]`(**本规范新增 · DRY helper**)

**封装了"调 resolve_active_overlay + 打印 stderr scope banner"的样板代码** · 让 CLI main() 一行搞定。
当前 `aether_tasks / aether_daily / aether_doctor` 各自抄了一份 `_activate_overlay()` · 统一到此。

- 输入:`args`(argparse Namespace · 读 `args.path`)· `announce`(是否打印 scope banner 到 stderr)
- 返回:`(overlay_dir, source_label)`
- 副作用:若 announce · stderr 写一行 `  · scope: <name> [(via <source>)]`

---

## §3 · CLI 归属类别登记表

每个 `aether_*.py` 文件**必须**属于且仅属于以下 4 类之一。

### 产品角色三元分类(Day 14 新增 · 对标 nuwa-skill 生产者-消费者-进化者架构)

除了运行时分类(OVERLAY-AWARE / CORE-READER / HOOK-DRIVEN / CENTRAL-ONLY)外,**每个 CLI 再归一个产品角色**:

- **[P] 生产者**(Producer):创建 / 初始化 / 装配基础设施和身份数据
- **[C] 消费者**(Consumer):运行时被调用 · 读数据 → 产出当前结果
- **[E] 进化者**(Evolver):对现有数据做诊断 · 建议 · 重写 · 归档(让系统自我改进)

产品角色正交于运行时 scope · 一个 CLI 可以既是 OVERLAY-AWARE 又是 Producer(如 `aether_project`) · 一个 CLI 可以既是 CENTRAL-ONLY 又是 Evolver(如 `aether_critic`)。

launch 时的产品叙事 = **"一个反射弧(Consumers)+ 一套进化引擎(Evolvers)+ 极简装配(Producers)"** · 不是"26 个零碎 CLI"。

---

### 3.1 **OVERLAY-AWARE**(per-project · 写读当前 overlay)

职责:处理"本项目的" events / coll / tasks / index / state。
必须:调 `activate_overlay_for_cli(args)` · 加 `--path` flag · stderr 打印 scope banner。

| 文件 | 角色 | 数据路径 | 当前状态 |
|---|---|---|---|
| `aether_tasks.py` | [C] | overlay/tasks.jsonl | ✅ 已迁(Day 11) |
| `aether_daily.py` | [C] | overlay/guardian-state + events | ✅ 已迁(Day 11) |
| `aether_doctor.py` | [E] | overlay/{index.db, state, tasks} | ✅ 已迁(Day 11)· fix_command Day 13 修 |
| `aether_indexer.py` | [C] | overlay/{events, index.db, ingest-state} | ✅ Day 13 迁 |
| `aether_guardian.py` | [C] | overlay/{guardian-state, index.db} | ✅ Day 13 迁 |
| `aether_autopilot.py` | [C] | overlay/{guardian-state, autopilot-state} | ✅ Day 13 迁 |
| `aether_session_summarizer.py` | [E] | overlay/{events, coll-drafts, state} | ✅ Day 13 迁 |
| `aether_query.py` | [C] | overlay/index.db | ✅ Day 13 迁 |

### 3.2 **CORE-READER**(读 `~/.aether-core/` · 不写)

职责:从 `core/` 读 pact / fields / species 用于 briefing / mode-activation。

| 文件 | 角色 | 数据路径 | 当前状态 |
|---|---|---|---|
| `aether_handshake.py` | [C] | core/pact + central/gen4-fields | ✅ scope-aware (Day 9 + Day 10) |
| `aether_federate.py` | [P] | core/{pact, fields, species-registry} | ✅ Day 10 · 唯一 core writer |
| `aether_project.py` | [P] | overlay/{manifest, subdirs} | ✅ Day 10 · overlay bootstrap |

### 3.3 **HOOK-DRIVEN**(按 payload 路由 · 不扫 cwd)

职责:Cursor hook 调用,`payload.workspace_roots[0]` 决定路径。

| 文件 | 角色 | 路由方式 | 当前状态 |
|---|---|---|---|
| `aether_hook.py` | [C] | `resolve_overlay_dir(payload)` | ✅ Day 9 |
| `aether_events.py` | [C] | 同上(delegates) | ✅ Day 12 |

### 3.4 **CENTRAL-ONLY**(设计上只处理 Aether 源码完整性)

职责:对 Aether 源代码本身做保护 / 审计 / 备份 · 与任何 per-project overlay **无关**。

> **不要**把这类工具也改成 overlay-aware · 它们的本职就是 central。强行迁会破坏"整个 Aether 源代码的 SHA256 基线"这个语义。

| 文件 | 角色 | 为什么是 central-only | 当前状态 |
|---|---|---|---|
| `aether_integrity.py` | [E] | baseline 是 Aether 源代码树的 SHA256 · guest 项目不包含源代码 | ✅ 规范明示 |
| `aether_snapshot.py` | [E] | 备份 aether/ 目录 · 不备份 guest 项目文件 | ✅ 规范明示 |
| `aether_payload_schema.py` | [E] | `.cursor/hooks/.discovery/` 只存在于 workspace-level,没有 per-project 概念 | ✅ 规范明示 |
| `aether_selfcheck.py` | [E] | 自检的是 Aether 架构本身 · L0-L10 都是源码层 | ✅ 规范明示 |
| `aether_critic.py` | [E] | 扫 central/gen4-fields + central/gen6-coll · 对源代码出诊断 | ✅ 规范明示 |
| `aether_evolve.py` | [E] | 从 critic 报告生成 ep-*.md proposal · 演化 fields/species | ✅ 规范明示 |
| `aether_calibrate.py` | [E] | 根据 essence + coll 调 field 浓度 · 是 field 演化前置 | ✅ 规范明示 |
| `aether_promote.py` | [E] | nursery seed → registered species · 生态演化 | ✅ 规范明示 |
| `aether_seeds.py` | [E] | nursery seed 清理 + 晋升候选分析 | ✅ 规范明示 |
| `aether_persona.py` | [E] | 根据 coll 统计合成 AI persona 向量 | ✅ 规范明示 |
| `aether_stats.py` | [C] | 发布 site/public/stats.json 给网站用 | ✅ 规范明示 |
| `aether_archive.py` | [E] | 冷数据归档到 gen6-noesis/archive/ | ✅ 规范明示 |
| `aether_code_grader.py` | [E] | AI 代码产出评级 | ✅ 规范明示 |
| `aether_install.py` | [P] | 装到 `~/.cursor/` · 全局一次性 bootstrap | ✅ 规范明示 |

### 3.5 · 产品角色汇总(Day 14 launch 叙事)

| 角色 | CLIs | 产品意义 |
|---|---|---|
| **Producer [P]** · 3 | `aether_federate` / `aether_project` / `aether_install` | 一次性装配 · 新用户的"装机"步骤 |
| **Consumer [C]** · 10 | `aether_handshake` / `aether_hook` / `aether_events` / `aether_tasks` / `aether_daily` / `aether_indexer` / `aether_guardian` / `aether_autopilot` / `aether_query` / `aether_stats` | 日常反射弧 · Owner 真在用的那 4-5 个命令都在这里 |
| **Evolver [E]** · 13 | `aether_doctor` / `aether_session_summarizer` / `aether_critic` / `aether_evolve` / `aether_calibrate` / `aether_promote` / `aether_seeds` / `aether_persona` / `aether_archive` / `aether_code_grader` / `aether_integrity` / `aether_snapshot` / `aether_payload_schema` / `aether_selfcheck` | 系统自检 · 自批判 · 自改进 · Owner 不用背 · 后台跑 |

**观察**:13 个 Evolver · 数量上最多 · 但 Owner 日常关心度最低。这是对的 — **进化引擎应该静默** · 有问题才报警(doctor 绿则无声)。nuwa-skill 把 darwin.skill 独立出来做进化是同样思路。Aether 不需要拆 npm 包但**分类必须清楚**。

---

## §4 · 接口契约

### 4.1 `activate_overlay_for_cli(args, announce=True) -> tuple[Path, str]`

**必须**:

```python
def main():
    ap = argparse.ArgumentParser(...)
    ap.add_argument("--path", help="project root (default: walk up from cwd)")
    # ... 其他参数
    args = ap.parse_args()
    
    overlay, source = activate_overlay_for_cli(args, announce=not args.json)
    # overlay 现在就是本次命令的 .aether/
    # source ∈ {"explicit", "env", "discovered", "central"}
```

**禁止**:

```python
# 在模块顶部写死
DATA_DIR = WORKSPACE_ROOT / ".aether"  # ❌
```

**允许**(模块顶部设**默认值** · 但 main() 必须重赋值):

```python
# 默认指向 central 作为"尚未 activate" 状态 · 防止 import 时报错
DATA_DIR: Path = CENTRAL_OVERLAY  # ✓ 默认兜底

def main():
    global DATA_DIR
    overlay, _ = activate_overlay_for_cli(args)
    DATA_DIR = overlay  # 覆写
```

### 4.2 `--path` flag 约定

- 全局统一名称:`--path`(不得用 `--project-root / --workspace / --overlay`)
- 语义:项目根 · 函数内部会 `/ ".aether"` 自动拼
- 不存在时:`resolve_active_overlay` 仍返回路径 · 调用方 `if p.exists()` 决定是报错还是自建

### 4.3 Source banner 输出

- 写到 **stderr**(永不污染 stdout · 方便 `| jq`)
- 单行 · 格式:`  · scope: <name>` 或 `  · scope: <name>  (via <source>)`
- `--json` / `--quiet` 模式下必须 suppress

---

## §5 · 跨 scope 的数据依赖

OVERLAY-AWARE 工具在 guest 模式下运行时,仍然需要**只读**访问 core 的 fields / species。规则:

| 数据 | OVERLAY-AWARE 工具怎么读 |
|---|---|
| events.jsonl | **overlay**(必须)|
| coll-*.md(索引用) | overlay/coll/ (若存在) · 否则 central/gen6-noesis/collapse-events/(仅 central scope 下) |
| essence.md | **central/gen6-noesis/mirror**(overlay 不写这个 · 是 Owner 画像) |
| species-registry.json | core(若 init)· 否则 central/gen5-ecoware(fallback) |
| fields/*.field.md | core/fields(若 init)· 否则 central/gen4-morphogen/fields(fallback) |
| pact.md | core/pact.md(若 init)· 否则 central/labs/chronicle/collaboration-pact-2026-04-17.md(fallback) |

**原则**:可变的事件状态(events / coll / tasks / state)按 overlay 隔离 · 不变的身份资料(essence / species / fields / pact)跨项目共享 · 从 core 读。

---

## §6 · 幂等 / 失败模式 / 向后兼容

### 6.1 幂等

所有 state 写入(`indexer-state.json` / `guardian-state.json` / `autopilot-state.json` / `summarizer-state.json`):
- **内容未变 → 不 touch 文件**(避免 git noise + SSD 写入)
- 如何判断:读老文件 → 算 SHA → 比对 → 相等则 skip

### 6.2 失败模式

- **找不到 overlay**:默认 fallback `central` + stderr 警告 · **不静默创建新目录**
- **没有 core**:fields/species 读 central fallback · `aether federate init-core` 提示
- **hook 收到空 payload**:fall back 到 central(不 crash)· `aether_hook.py` 已有逻辑

### 6.3 向后兼容

- 模块级 `DATA_DIR = CENTRAL_OVERLAY` 默认值**不删**(老的 `from X import DATA_DIR` 仍能工作)
- 公开函数签名不变 · 只加可选 kwargs
- `resolve_data_dir(payload)` 保留 alias · 委托给 `resolve_overlay_dir`

---

## §7 · 测试矩阵

任何迁移 PR 必须验证以下 3 × N 矩阵(N = 被改 CLI 数):

| scope | 测试命令 | 期望结果 |
|---|---|---|
| `central` | `cd <central>; python bin/<tool>.py <args>` | 写读 `<central>/.aether/` · banner `scope: 制作skills的skiils` |
| `guest` | `cd <some-project>; aether project init --apply; aether <tool>` | 写读 `<some-project>/.aether/` · banner `scope: <some-project>` |
| 无 overlay | `cd C:\Windows\Temp; python <tool>` | fallback central · banner `scope: central (no .aether/ found ...)` |

手工验证脚本(可选 · 对应 PR 提供):

```powershell
# central
cd C:\Users\33116\OneDrive\桌面\制作skills的skiils
python aether/bin/aether_indexer.py stats

# guest(真 guest 项目)
cd $env:TEMP\test-overlay
python C:\Users\33116\OneDrive\桌面\制作skills的skiils\aether\bin\aether_project.py init --apply
python C:\Users\33116\OneDrive\桌面\制作skills的skiils\aether\bin\aether_indexer.py ingest

# 无 overlay
cd C:\
python C:\Users\33116\OneDrive\桌面\制作skills的skiils\aether\bin\aether_indexer.py stats
# 应看到 banner: scope: central (no .aether/ found ...)
```

---

## §8 · 违规检测

在 `aether_selfcheck.py` 将来可加一项 L11 检查(**非本次 PR · 未来的 P2**):

- 扫 `aether/bin/aether_*.py`
- 扫 `grep -n 'WORKSPACE_ROOT\s*/\s*["\']\.aether["\']'`
- 排除登记表中 **CENTRAL-ONLY** 的文件
- 其他文件出现此模式 = warn "path hardcoded · should use resolve_active_overlay"

留作未来 P2 任务 · 本次不加 selfcheck layer(守 Day 9 承诺)。

---

## 附录 A · 本规范的权威顺位

> 本文 > 任何 .py 模块 docstring > coll-*.md > handover

当 .py 文件和本规范冲突:**改 .py**,不要改规范。
规范本身变更:PR + 在 coll-NNNN 留痕 + 本文 version bump。

---

## 附录 B · Field 证据等级规范(Day 17 · coll-0088 落地)

> 本附录补 Day 15 POC 时留的路径 · 把 `*.field.md` 维度表证据列的 4 级标注固化为规范。

### B.1 四级定义

每个 field 维度表必须有 `证据` 列 · 值取以下一:

| 符号 | 等级 | 条件 |
|---|---|---|
| 🟢 | 强 | 外部公开来源 ≥ 1 条 **且** Aether 内部 coll 正文复现 ≥ 3 次 |
| 🟡 | 中 | 外部来源 ≥ 1 条 **或** 内部复现 ≥ 1 次(两头至少一个有)|
| 🔴 | 弱 | 两头都 0 · **Day N evolve 候选**(剪 / 降权 / 合并 / 补触发用例 四选一)|
| ⚪ | 特殊 | 本性不出现在对话文本中(元数据 · 静态标签)· **不该在维度表** · 应移入 YAML frontmatter |

### B.2 证据列字符串格式

```
🟢 ext + coll: N/M(coll-XXXX / coll-YYYY)
🟡 ext · coll: 0/M  (或)  🟡 ext + coll: 1/M(coll-ZZZZ)
🔴 coll: 0/M · Day N evolve 候选
⚪ 元数据 · 不测文本复现
```

其中:
- `ext` = 外部来源(传记 / 著作 / 公开访谈 / 产品文档) · 标记 `(training-recall · 需 Owner 人力复核)` 若由 AI 训练知识给出
- `coll: N/M` = 维度名在 M 个 coll 正文里出现 N 次(**不算 Fields active 行的 field id** · 只算正文)
- `ext + coll` 两头都有:用 `+`
- `ext · coll: 0/M` 只有外部:用 `·`

### B.3 证据备忘段 · 强制

每个 field 的核心浓度向量表下方必须有 `### 证据备忘(Day N 新增 / evolve)` 子节 · 写三块内容:

1. **外部来源**:每个维度的公开引用(可用 training-recall 承认不确定性 · 不装严谨)
2. **内部复现**:每个维度在 coll 里的真实出现情况(从 `*.field.md` 里的死维度 · 到 evolve 决策的一手数据)
3. **evolve 决策**(有则写):本次动了哪些数值 / 哪些从维度表移出 / 哪些加门控 / 对应 `ep-NNNN.md`

### B.4 Evolve 动作清单

当 🔴 弱证据维度被识别 · Evolve 动作五选一(不是二选一的"剪"或"留"):

| 动作 | 符号 | 适用场景 |
|---|---|---|
| 剪(delete) | 🗑️ | 外部无来源 · 内部 0 复现 · 并入其他维度无损 |
| 降权(downweight) | ↓ | 外部证据强但 Aether 场景超配 · 保留但调低 |
| 合并(merge) | ⊕ | 与另一维度语义高度重叠 · 保留语义合并变量 |
| 加门控(scope-gate) | 🚪 | 维度正确但触发场景有限 · 仅在特定上下文激活 |
| 移元数据(move-metadata) | 📋 | 静态属性误入维度表 · 迁 YAML frontmatter |

**ep-0002 示例动作分布**:
- 降权 × 4(rigor 的 4 维度)
- 合并的变体 × 1(bullshit 共享承诺 · 不真删两 style 场)
- 加门控 × 1(ive.material_awareness)
- 移元数据 × 2(linus / ive 的 humor_type)
- 调值 × 1(linus.empathy)

### B.5 为什么这个规范比 nuwa-skill 的"三重验证"硬

nuwa-skill 的维度准入靠 AI 自裁:"跨 2+ 领域 / 有预测力 / 有排他性" · 三项都是主观判断。

Aether 的证据等级:
1. **🟢 强**有**两个可量化条件**(ext ≥ 1 · coll ≥ 3)· 都可被 Owner / 第三方 grep 验证
2. **⚪ 特殊**明确承认"有些维度不该出现在对话文本" · 不把它们算进"死维度"冤案
3. **🔴 弱的 evolve 动作有 5 种精细选择** · 不是只有"剪 vs 留"二元

**具体对比**:nuwa 的 trump-skill 里 `directness = 0.95` · 你作为用户无法知道这个 0.95 是怎么得出的。Aether 的 linus-torvalds.field.md 告诉你:`precision = 0.95 · 🟢 ext + coll: 3/79(coll-0067 / coll-0084)`— 你能点开那两个 coll 看真实用例。

---

---

## 附录 C · Day N 定义规范(v1.2 · 2026-04-22 · coll-0089 落地)

> 本附录固化 Day 10 session 5 发现的"Day N 定义模糊"架构 bug 的修复规范。
>
> **场景**:AI 在同一 session 内自由发挥 · coll 里声称"Day 13 / 14 / 15 / 17"(自编)· 与 handshake 算出的 Day 10 不一致 · 系统无法检测 · Owner 从 status line 发现矛盾。本附录规定**唯一权威来源**。

### C.1 Day N 的 3 个源与权威顺位

| 顺位 | 来源 | 算法 | 现值(2026-04-22)|
|---|---|---|---|
| **1**(权威) | status line 注入 | handshake `current_day()` 函数 · 优先级 handover > plan > pact | **Day 10** |
| 2 | handover 文件最大编号 + 1 | `aether/docs/daily/day-*-handover.md` 最大 · +1 | Day 10(= day-9 + 1)|
| 3(fallback) | pact 日期算 | `(today - 2026-04-17).days + 1` | Day 6 |

**唯一权威 = 顺位 1** = status line。AI **只读这一个** · 不自算。

### C.2 同 session 多 coll 的命名规则

当**同一次 Owner 命令 → AI 工作回合**产出多个 coll:

- **全部用 status line 的 N · 不递增**
- **用子编号区分**:`Day N · session 1` / `Day N · session 2` / ...
- coll 文件名仍按 coll-NNNN.md 递增(这是 coll 编号 · 不是 Day 编号)

**示例**(Day 10 session 5 之后):

```
coll-0085 · Day 10 · session 1  (联邦 D 层)
coll-0086 · Day 10 · session 2  (nuwa 对标)
coll-0087 · Day 10 · session 3  (field 证据列)
coll-0088 · Day 10 · session 4  (ep-0002 applied)
coll-0089 · Day 10 · session 5  (Day N 修复 · 本附录生成)
coll-0090 · Day 11 · session 1  (下次 Owner 开 chat · Day 自增)
```

### C.3 Handover 的强制写入时机

**session 末必须写 `day-N-handover.md`** · 否则 status line 下次无法前进。

什么是 "session 末":
- Owner 明确说 "保存" / "今天到这"
- Owner 长时间无回复(AI 无法判断)
- AI 做完 P0 清单(主动总结)
- Owner 触发"复盘" / "handover" / "交接"

**handover 文件名**:`day-N-handover.md` · 其中 N = 当前 session 的 Day N(同 §C.2)。
**写完 handover 意味着**:下次 session status line 会推到 **Day N+1**。

### C.4 失败模式与检测(留待 selfcheck L11)

当前 Aether 缺少对"AI 自编 Day N"的自动检测。Day 11+ 应在 selfcheck 加一层 L11:

```python
# 伪代码
def check_l11_day_n_consistency():
    latest_handover_n = int(re.match(r'day-(\d+)', latest_handover().name).group(1))
    expected_n = latest_handover_n + 1  # status line N
    
    # 扫最近 10 个 coll 的 Date 字段
    for coll in latest_colls(10):
        date_line = re.search(r'Date\*\*:\s*\S+\s*·\s*Day\s+(\d+)', coll.read_text())
        if date_line:
            coll_n = int(date_line.group(1))
            if coll_n > expected_n:
                yield Warn(f"{coll.stem}: Day {coll_n} > expected {expected_n}")
```

**目前**:靠 AI 自觉(AGENTS.md §3.7)+ Owner 视觉发现(如 Day 10 session 5 这次)。
**未来**:L11 自动拦截。

### C.5 本规范为什么是架构级的

1. Aether 的**所有时间推进**最终依赖 Day N(30 天计划 / tasks --day / coll Date / handover 文件名)
2. 如果 Day N 可以被 AI 自编 · 则**所有时间字段都不可信**
3. 产品叙事(launch · 健康分轨迹)基于"Day N 增长" · 虚假 Day N = **虚假产品承诺**

**Day 10 session 5 的 bug 是 Aether 历史第一次"数据完整性"级别的 architecture bug**。联邦记忆(Day 9-12)解决了"数据去哪里" · field 证据化(Day 10 S1-S4)解决了"数据从哪来" · Day N 修复(Day 10 S5)解决了"数据的时间坐标是否真实"。三者加起来 · Aether 的数据层才算完整。

---

## §8 · Status Line Scope 分叉(Day 12 · coll-0092)

### §8.1 · 背景

Day 9 fix hook 层 read/write asymmetry(coll-0081)· Day 10 落地 overlay 基础设施(coll-0082)· Day 11 修 CLI 层(coll-0083)。**但 status line 自己没修** —— `_status_line` 在 dev-self 和 guest 两种 scope 下拼的都是中央的 Day / 评分 / handover · 只换了 scope 贴纸。

Day 12 Owner 在 `cursor-api-proxy` 项目里看到中央 `Day 12/30 · 100/100 · handover: day-11-handover.md` 字样 · 发现跨项目概念污染。根因 + 修复方案见 `aether/docs/STATUS-LINE-SCOPE-FIX.md`。

### §8.2 · 4 种 scope 的 status line 形态(唯一定义)

| scope | overlay 存在? | overlay/handover/ 有文件? | status line 形态 |
|---|---|---|---|
| `dev-self` | N/A | N/A | `Day N/30 · <score> · scope: dev-self · handover: day-N-handover.md` |
| `guest` | ✅ | ✅ | `Day N/30 · ?/? · scope: guest @ X · handover: day-N-handover.md` |
| `guest` | ✅ | ❌(刚 init) | `Day 1/30 · ?/? · scope: guest @ X · handover: day-0-handover.md` |
| `guest` | ❌ | — | `unregistered · scope: guest @ X · handover: none` |

**regex**(见 `.cursor/rules/aether.mdc` RULE 00):

```
registered:    ^⟁ Aether · Day \d+/30 · .+? · scope: [^·]+ · handover: day-\d+-handover\.md$
unregistered:  ^⟁ Aether · unregistered · scope: guest @ [^·]+ · handover: none$
```

`.+?` 是非贪婪 · 容纳 `86/100 (32 ok · 2 warn · 3 fail)` 这种含内部 `·` 的评分段;`[^·]+` 用于 scope 段因为它不含 `·`。对应 fixtures 在 `aether/tests/test_status_line_regex.py`。

### §8.3 · 读函数归属(single source of truth)

所有 Day N / 评分 / handover_name 的 **生产**必须走这三个函数(均在 `aether_handshake.py`)· 其他 .py **不得重新实现**:

| 函数 | 返回值 | dev-self 行为 | guest 行为 |
|---|---|---|---|
| `current_day_for_scope(scope, overlay_dir)` | `str \| None` | 走原 `current_day()` | overlay handover max N + 1 · 无 overlay → None |
| `selfcheck_score_for_scope(scope, overlay_dir)` | `str` | 走原 `selfcheck_score()` | 恒返 `?/?`(待 Day 13+ `--overlay` 模式) |
| `handover_name_for_scope(scope, overlay_dir)` | `str` | 走原 `latest_handover().name` | overlay 最新 handover 名 · 或 `"day-0-handover.md"` / `"none"` |

`_status_line()` 把 `day=None` 识别为 unregistered 分支 · 渲染短形式。

### §8.4 · 数据隔离边界更新

§1.1 `central scope` 与 §1.2 `guest scope` 的**数据位置**定义不变 · 但 **status line 的取值来源**从"永远是中央"改为"按 scope 分叉":

```
旧:   status line.Day → latest central handover + 1
      status line.score → 中央 selfcheck
      status line.handover → 中央最新 handover 名

新:   status line.Day → scope=dev-self ? 中央 : (overlay + 1 或 None)
      status line.score → scope=dev-self ? 中央 : "?/?"
      status line.handover → scope=dev-self ? 中央最新 : (overlay 最新 或 "none")
```

### §8.5 · AI 行为约束

当 status line 进入**不同 scope 形态**时 · AI 在本 session 写文档的行为边界:

| 形态 | AI 写 coll 用的 Day N | AI 引用 handover |
|---|---|---|
| `dev-self` | status line 的 N | 中央 handover |
| `guest + Day N/30` | status line 的 N(**该项目自己的 N**) | overlay/handover/ 下的 handover · **不引用**中央 |
| `guest + unregistered` | **不写 coll**(没有 Day 坐标)· 若要写 · 先建议 Owner `aether project init` | — |

**违反**:AI 在 guest 项目引用中央 Day 11 handover → cross-scope pollution · 由 `check_l11_day_consistency(overlay_dir)` 的 overlay-aware 版(Day 13+)拦截。当前靠 AGENTS.md §3.7 + AI 自觉。

---

_Spec version: **v1.3** · 2026-04-22(coll-0092 · Day 12)_
_v1 → v1.1 changes: +Appendix B(Field Evidence Grading · 5 evolve actions)_
_v1.1 → v1.2 changes: +Appendix C(Day N Definition · bug 发现于 coll-0089)_
_v1.2 → v1.3 changes: +§8(Status Line Scope Fork · bug 发现于 coll-0092)_
_Supersedes: 无_
_Next review: Day 13+ · 若 selfcheck `--overlay` 落地 · 再 v1.4_
