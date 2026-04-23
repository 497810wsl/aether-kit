# Status Line Scope Fix · 设计方案(v1 · 待审)

> **状态**:pending Owner review · 未动代码
> **触发**:Day 12 · Owner 在 `cursor-api-proxy` 项目里发现 status line 贴中央 `Day 12/30 · 100/100 · handover: day-11-handover.md` · 跨项目污染
> **作者**:AI(linus=0.9 · rigor=0.9)· 2026-04-22
> **评审目标**:Owner 一次读完 · 在末尾 §10 勾 approve / reject / modify · 不再需要第二轮设计讨论

---

## §0 · TL;DR(30 秒版)

当前:**guest project 的 status line 照抄中央 dev-self 的 Day/评分/handover** · 跨项目概念污染 · 命令误投。

修:**status line 按 scope 分叉 4 种形态**(dev-self / guest+overlay+handover / guest+overlay空 / guest+unregistered)· 改 2 个 .py + 1 条 regex + 3 处文档。约 **180 行代码新增** · 约 **60 行文档更新** · **零破坏性重命名**(只新增分支 · 不删 dev-self 路径)。

---

## §1 · 证据(bug 实锤)

### 1.1 · Owner 截图(原始证据)

```
⚠ Aether · Day 12/30 · 100/100 (31 ok · 0 warn · 0 fail) · scope: guest @ cursor-api-proxy
[mode: CODE-REVIEW+CODE-WRITE · fields: diagnosis, root-cause, fix-plan, implementation]
```

**问题**:
- `Day 12/30` 是中央 Aether 自己 30 天实验进度 · `cursor-api-proxy` 可能根本没这个契约
- `100/100 (31 ok · 0 warn · 0 fail)` 是中央 selfcheck 分 · 和 cursor-api-proxy 的代码质量无关
- `handover: day-11-handover.md` 默认指向中央 Aether-dev handover · 其 P0 是"形态 α/β/γ 决策" · **对 guest project 是命令错投**

### 1.2 · 代码证据(`aether_handshake.py`)

原作者**明确承认**这是设计决定 · 不是疏忽:

```239:250:aether/bin/aether_handshake.py
def current_day() -> str:
    """Derive current day number from central handover names · fallback chain.

    Signal 1 (primary): latest handover file name (day-N-handover.md written
        end of Day N → today = Day N+1). Updates every session end.
    Signal 2 (backup): 30-day-plan.md progress bar.
    Signal 3 (fallback): pact date arithmetic (2026-04-17 = Day 1).

    Day N/30 is OWNER-scoped (not project-scoped) · same value across guest
    projects · Owner's 30-day commitment doesn't pause when they switch repos.
    """
```

理由陈述为"Owner 的 30 天承诺不会因切换 repo 而暂停"· 但这把**个人契约**和**软件语义**混淆了(§2 展开)。

### 1.3 · 拼装点(`_status_line`)

```298:313:aether/bin/aether_handshake.py
def _status_line(day: str, score: str, scope: str, scope_detail: str,
                 handover_name: str) -> str:
    """Build the mandatory RULE 00 status line.

    Format MUST match aether.mdc regex:
      ^⟁ Aether · Day \\d+/30 · \\d+/100 .* · handover: day-\\d+-handover\\.md$
    ...
    """
    if scope == "dev-self":
        tag = "scope: dev-self"
    else:
        tag = f"scope: guest @ {scope_detail}"
    return f"⟁ Aether · Day {day}/30 · {score} · {tag} · handover: {handover_name}"
```

**三个数据源(day / score / handover_name)对两种 scope 用同一份** · scope 只是贴标签 · 没真正分叉。

### 1.4 · read/write asymmetry 第三季

- Day 9 fix(coll-0081)· hook 写数据按 payload.workspace_roots 隔离 ✓
- Day 10 fix(coll-0082)· `aether project init` 建 overlay 基础设施 ✓
- Day 11 fix(coll-0083)· CLI 层 `aether_tasks/daily/doctor` 读 overlay ✓
- **Day 12 漏**:**status line 仍读中央** · 这是 asymmetry 的最后一段

`day-11-handover.md` L58 明写 "Day 11 closes the loop" · **实际上没 close** · status line 没包含在 Day 11 的扫荡范围里。

---

## §2 · 根因分析

### 2.1 · 概念混淆

原注释 "Owner's 30-day commitment doesn't pause when they switch repos" 把两件事混一起了:

| 事物 | 归属 | 生命周期 |
|---|---|---|
| Owner 的 30 天 Aether 实验契约 | `pact.md`(个人承诺文件) | 跨项目有效 |
| Aether 软件本身的"Day 12" | `day-11-handover.md`(dev-self 日志) | **只在中央 repo 有意义** |

真正跨项目的是**前者**(pact.md 里的 "2026-04-17 开始 · 承诺 30 天") · 那是 Owner 的事 · 应该在 guest briefing 以**身份 / identity** 方式展示(现已通过 `_build_guest_briefing` L511-523 的 pact 段展示)。

**不该**跨项目的是**后者**(handover 推进 / 中央 selfcheck 分) · 那是 Aether 自己的产品开发日志。

### 2.2 · "Day N/30" 字面的语义冲突

在 guest project 语境下 · 同一行 "Day 12/30" 有三种可能的解读:

1. "Owner 的 Aether 实验第 12 天"(原设计意图 · 但对 guest 开发者无用)
2. "cursor-api-proxy 用 Aether 的第 12 天"(Owner 直觉 · 但目前**不是事实** · 它第 0 天)
3. "cursor-api-proxy 自己的 30 天迭代第 12 天"(泛化可能 · 但没定义)

**三义 = 歧义 = bug**。fix 的本质是**让语义唯一**。

### 2.3 · RULE 00 contract 与数据分离不彻底

RULE 00 regex 要求 status line 必须含 `Day \d+/30 · \d+/100` · 这本来是为 Owner **肉眼验证 hook 触发了**。但这个 contract 把"hook 工作了"和"中央 Aether 有这些数值"绑死了 —— 在 guest 没 overlay 时根本没有这些数值。

---

## §3 · 目标行为(4 种 scope 的真值表)

### 3.1 · 4 种运行态

| # | scope | overlay 存在? | overlay/handover/ 有文件? | 期望 status line 形态 |
|---|---|---|---|---|
| **S1** | `dev-self`(cwd == central) | N/A | N/A | `⟁ Aether · Day 12/30 · 86/100 (32 ok · 2 warn · 3 fail) · scope: dev-self · handover: day-11-handover.md` **(保持不变)** |
| **S2** | `guest` | ✅ | ✅ 有 1+ day-N-handover.md | `⟁ Aether · Day N+1/30 · ?/? · scope: guest @ X · handover: day-N-handover.md` |
| **S3** | `guest` | ✅ | ❌(刚 init 过 · 空文件夹) | `⟁ Aether · Day 1/30 · ?/? · scope: guest @ X · handover: day-0-handover.md` |
| **S4** | `guest` | ❌ | N/A | `⟁ Aether · unregistered · scope: guest @ X · handover: none` |

### 3.2 · 各字段取值表

| 字段 | S1 dev-self | S2 guest+handover | S3 guest+empty | S4 unregistered |
|---|---|---|---|---|
| Day N | 中央 handover 最大 N + 1 | overlay handover 最大 N + 1 | `1` | (省略 · 用 `unregistered` 占位) |
| `/30` | 存在 | 存在 | 存在 | (省略) |
| score | 中央 selfcheck | `?/?`(**Day 13 加 `--overlay` 模式**) | `?/?` | (省略) |
| scope tag | `scope: dev-self` | `scope: guest @ X` | `scope: guest @ X` | `scope: guest @ X` |
| handover 字段 | 中央最新 handover 文件名 | overlay 最新 handover 文件名 | `day-0-handover.md` | `none` |

### 3.3 · 配套 briefing body 建议

在**status line** 之外,briefing body 里针对每种 scope 给 AI 一行"下一步指引":

| scope | body 加一行 |
|---|---|
| S1 | 不加(原 dev-self briefing 已完备) |
| S2 | 不加(overlay handover 本身就是命令) |
| S3 | `_This project just registered · no handover yet · help Owner plan this project's Day 1._` |
| S4 | `_This project is unregistered · suggest Owner: \`aether project init --apply\` (only if they want per-project Aether state) · otherwise do normal work._` |

**注意 S4 措辞**:不是强命令让 Owner init · 是"建议" · 因为 Owner 可能**故意**不 init(单次帮忙的 repo · 不需要持久记忆)。

---

## §4 · 代码改动清单

### 4.1 · 文件清单(7 个)

| # | 文件 | 改动类型 | 预估行数 |
|---|---|---|---|
| 1 | `aether/bin/aether_handshake.py` | 新增 scope-aware 读函数 + 改 `_status_line` | +120 / -20 |
| 2 | `aether/bin/aether_selfcheck.py` | L11 改为**读 active overlay 的 handover**(不只是中央) | +30 / -10 |
| 3 | `.cursor/rules/aether.mdc` | RULE 00 regex + 说明改写 | +15 / -10 |
| 4 | `aether/AGENTS.md` | §3.7 Day N 权威说明更新(scope-aware) | +20 / -5 |
| 5 | `aether/docs/PATH-RESOLUTION-SPEC.md` | 新增 §8 · status line 分叉规范 | +60 |
| 6 | `aether/gen6-noesis/collapse-events/coll-0092.md` | **新文件** · 记录这次 Owner-discovery bug | +80 |
| 7 | `aether/docs/daily/day-12-handover.md` | **新文件** · Day 12 session 交接 | +100 |

**不改 / 明确 out-of-scope**(§8 展开):
- `~/.cursor/rules/aether.mdc`(全局)· 同步更新 · 但不在代码仓 · 由 Owner 手动 sync 或 reinstall
- `aether_install.py` · install 不变(还是写那同一份 rules) · 只要 rules 本身改了就行
- `aether_events.py` / `aether_paths.py` · 路径层已对 · 不动
- `aether_project.py` · overlay 初始化已对 · 不动

### 4.2 · `aether_handshake.py` · 新增 API(精确 pseudo-diff)

#### 4.2.1 · 新增顶层函数

```python
# ───── scope-aware readers (新增 · 在 current_day 上面) ─────

def _latest_local_handover(overlay_dir: Path) -> Path | None:
    """Read overlay/handover/day-*-handover.md · max N."""
    ho_dir = overlay_dir / "handover"
    if not ho_dir.exists():
        return None
    files = list(ho_dir.glob("day-*-handover.md"))
    if not files:
        return None
    def day_num(p):
        m = re.match(r"day-(\d+)-handover\.md", p.name)
        return int(m.group(1)) if m else -1
    return max(files, key=day_num)


def current_day_for_scope(scope: str, overlay_dir: Path | None) -> str | None:
    """Return Day N string · or None when unregistered (no overlay).

    dev-self: 中央 handover + 1 (current_day() 原逻辑)
    guest + overlay + handover exists: overlay handover + 1
    guest + overlay + no handover: "1"
    guest + no overlay: None (signals unregistered)
    """
    if scope == "dev-self":
        return current_day()
    if overlay_dir is None or not overlay_dir.exists():
        return None
    ho = _latest_local_handover(overlay_dir)
    if ho is None:
        return "1"  # freshly registered · no handover yet
    m = re.match(r"day-(\d+)-handover\.md", ho.name)
    return str(int(m.group(1)) + 1) if m else "1"


def selfcheck_score_for_scope(scope: str, overlay_dir: Path | None) -> str:
    """Central selfcheck only makes sense for dev-self.

    Day 13 follow-up: add `aether_selfcheck.py --overlay <path>` to
    score overlay health · until then, guest shows '?/?'.
    """
    if scope == "dev-self":
        return selfcheck_score()
    return "?/?"


def handover_name_for_scope(scope: str, overlay_dir: Path | None) -> str:
    """'none' when no overlay, else overlay's latest or day-0-handover.md."""
    if scope == "dev-self":
        ho = latest_handover()
        return ho.name if ho else "day-0-handover.md"
    if overlay_dir is None or not overlay_dir.exists():
        return "none"
    ho = _latest_local_handover(overlay_dir)
    return ho.name if ho else "day-0-handover.md"
```

#### 4.2.2 · 改写 `_status_line`

```python
def _status_line(day: str | None, score: str, scope: str,
                 scope_detail: str, handover_name: str) -> str:
    """Build the mandatory RULE 00 status line.

    day=None + handover_name='none' signals "unregistered" state · renders
    shortened form that still satisfies RULE 00 regex.

    Format alternatives:
      registered:    ⟁ Aether · Day N/30 · <score> · scope: <tag> · handover: day-N-handover.md
      unregistered:  ⟁ Aether · unregistered · scope: <tag> · handover: none

    Regex MUST match aether.mdc:
      ^⟁ Aether · (Day \\d+/30 · [^·]+|unregistered) · scope: [^·]+ · handover: (day-\\d+-handover\\.md|none)$
    """
    if scope == "dev-self":
        tag = "scope: dev-self"
    else:
        tag = f"scope: guest @ {scope_detail}"

    if day is None:  # S4 · unregistered
        return f"⟁ Aether · unregistered · {tag} · handover: none"
    return f"⟁ Aether · Day {day}/30 · {score} · {tag} · handover: {handover_name}"
```

#### 4.2.3 · 改 `_build_guest_briefing` 调用点

```python
# 原(L457-462):
#   day = current_day()
#   score = selfcheck_score()
#   ho = latest_handover()
#   handover_name = ho.name if ho else "day-0-handover.md"
#   proj_name = _short_project_name(ws_root)
#   status_line = _status_line(day, score, "guest", proj_name, handover_name)

# 新:
overlay_dir = ws_root / ".aether"
day = current_day_for_scope("guest", overlay_dir)
score = selfcheck_score_for_scope("guest", overlay_dir)
handover_name = handover_name_for_scope("guest", overlay_dir)
proj_name = _short_project_name(ws_root)
status_line = _status_line(day, score, "guest", proj_name, handover_name)
```

#### 4.2.4 · S4 briefing body 补一句

`_build_guest_briefing` 里 `has_overlay = False` 分支原文:

```python
# 原 L617-625:
lines.append(
    "No project-local Aether overlay yet. Nothing cross-contaminates "
    "from the central Aether-dev workspace. Work normally."
)
lines.append("")
lines.append(
    "_To give THIS project its own handover / coll / tasks ledger · "
    "run `aether project init --apply` in the project root._"
)
```

**不改**(已够清晰 · 和 S4 status line 的 `unregistered` 形态呼应)。

### 4.3 · `aether_selfcheck.py` · L11 改为 overlay-aware

**当前问题**:L11 永远读 `ROOT / "docs" / "daily"`(中央 handover)和 `WORKSPACE_ROOT / ".aether" / "tasks.jsonl"`(中央 tasks)。在 guest 项目里跑 `aether selfcheck` 会用中央数据评分 · 没意义。

**改动**:`check_l11_day_consistency()` 加 `overlay_dir` 参数(可选 · 默认中央)· 跑 selfcheck 时由 main() 从 `resolve_active_overlay()` 取:

```python
# 大致改动(精确 diff 留到实施):
def check_l11_day_consistency(overlay_dir: Path | None = None) -> list[Check]:
    # 默认 None → 走原中央逻辑(兼容)
    # 传 overlay_dir → 读 overlay/handover/ 和 overlay/tasks.jsonl
    handover_dir = (overlay_dir / "handover") if overlay_dir else (ROOT / "docs" / "daily")
    tasks_path = (overlay_dir / "tasks.jsonl") if overlay_dir else (WORKSPACE_ROOT / ".aether" / "tasks.jsonl")
    coll_dir = (overlay_dir / "coll") if overlay_dir else (ROOT / "gen6-noesis" / "collapse-events")
    # ... 其余逻辑不变
```

**注意**:这是 Day 13 HON 层的**配套**(`--overlay` 打通 selfcheck 才有意义) · 本次改动**只加 argument · 不接通调用** · 保持向后兼容。

### 4.4 · `.cursor/rules/aether.mdc` · RULE 00 新 regex

**旧**(L17-18):

```
sessionStart hook(`aether_handshake.py`)会把 status line 注入到 `additional_context` · 第一行匹配:

^⟁ Aether · Day \d+/30 · \d+/100 .* · handover: day-\d+-handover\.md$
```

**新**:

```
sessionStart hook(`aether_handshake.py`)会把 status line 注入到 `additional_context` · 第一行匹配以下任一:

^⟁ Aether · Day \d+/30 · [^·]+ · scope: [^·]+ · handover: day-\d+-handover\.md$   # dev-self · guest+registered
^⟁ Aether · unregistered · scope: guest @ [^·]+ · handover: none$                 # guest+未 init

**unregistered 语义**:当前项目未跑 `aether project init` · AI 第一行照贴该行 · 然后在回复里轻量建议 Owner 是否 init(不强命令)。
```

### 4.5 · `aether/AGENTS.md` · §3.7 Day N 硬约束

**旧措辞**(L90):

> **Day N 的唯一权威来源** = sessionStart hook 注入 `additional_context` 的 **status line** 里的那个数字

**新措辞**(追加):

> **Day N 的唯一权威来源** = sessionStart hook 注入 `additional_context` 的 **status line** 里的那个数字。
>
> **scope 敏感性**(Day 12 补丁 · coll-0092):
> - `scope: dev-self` → Day N 指**中央 Aether 开发**进度(本 repo 的 30 天实验)
> - `scope: guest @ X` → Day N 指**该项目用 Aether** 的进度(独立计数)
> - `unregistered` → **没有 Day 数**· AI 不应在回复中引用 Day 数字
>
> AI 在 guest project 回复中引用 Day N 时 · 意思是该项目的 Day N · **不是中央 Aether-dev 的 Day N**。

### 4.6 · `aether/docs/PATH-RESOLUTION-SPEC.md` · 新增 §8

在文件末尾加一个新 section:

```markdown
## §8 · Status Line Scope 分叉(Day 12 · coll-0092)

Day 9-11 fix 了 hook / CLI 层的 read/write asymmetry · **但 status line 本身没 fix**。
Owner 在 Day 12 `cursor-api-proxy` 里看到中央 `Day 12/30 · 100/100 · handover: day-11-handover.md`
才发现。根因见 `aether/docs/STATUS-LINE-SCOPE-FIX.md`。

### §8.1 · 4 种 scope 的 status line 形态

| scope | overlay 存在? | overlay/handover/ 有? | status line 形态 |
|---|---|---|---|
| dev-self | N/A | N/A | `Day N/30 · <score> · scope: dev-self · handover: day-N-handover.md` |
| guest | ✅ | ✅ | `Day N/30 · ?/? · scope: guest @ X · handover: day-N-handover.md` |
| guest | ✅ | ❌ | `Day 1/30 · ?/? · scope: guest @ X · handover: day-0-handover.md` |
| guest | ❌ | — | `unregistered · scope: guest @ X · handover: none` |

### §8.2 · 读函数归属(single source of truth)

- `aether_handshake.current_day_for_scope(scope, overlay_dir)` —— Day N
- `aether_handshake.selfcheck_score_for_scope(scope, overlay_dir)` —— 评分(guest 暂固定 `?/?` · 待 Day 13 `--overlay` 模式)
- `aether_handshake.handover_name_for_scope(scope, overlay_dir)` —— handover 文件名

其他 .py 不得自行算 Day N / handover · 统一调这 3 个函数。
```

### 4.7 · `coll-0092.md` 新文件 · 大致内容

```markdown
---
coll_id: coll-0092
Date: 2026-04-22 · Day 12 · session N
Class: architecture-bug · Owner-observe-not-order
tags: [status-line, scope, cross-project-pollution, read-write-asymmetry]
---

## 本次语义

**Day 12 Owner 发现 status line scope 泄漏 · Day 9-11 的 read/write asymmetry 修复没覆盖到 status line 这一层 · 第 12 次 Owner-observe-not-order 模式**

(body · 参考 coll-0089/0090/0091 模板 · 约 80 行)
```

### 4.8 · `day-12-handover.md` 新文件 · 大致结构

```markdown
# Day 12 · 2026-04-22 · 任务交接档(Day 13 入口)

> 本 Day 的定性:**Owner observe-not-order (第 12 次) · 发现 status line 跨项目污染 · AI 出设计文档 · Owner 审 · AI 按设计实施**

## Day 12 战绩
- 跑 selfcheck --honest (78 → 86) · Day 11 Phase 5 改动生效
- ... (其余)

## Day 13 P0
- ... (根据实施结果填)
```

---

## §5 · Regex 迁移与 Callsites 审计

### 5.1 · regex 出现位置(grep 结果)

| 位置 | 性质 | 要更新? |
|---|---|---|
| `.cursor/rules/aether.mdc:18` | RULE 00 权威 regex | **必须更新**(见 §4.4) |
| `aether/bin/aether_handshake.py:63` | 注释引用 | 更新(文档同步) |
| `aether/bin/aether_handshake.py:303` | docstring 里 regex | 更新 |
| `aether/bin/aether_handshake.py:460` | `"day-0-handover.md" # regex safety` 注释 | 更新(解释 day-0 / none 二选一逻辑) |
| `aether/bin/aether_selfcheck.py:661` | `re.match(r"day-(\d+)-handover\.md", ...)` | 不用改(只解析真实 handover 文件名 · 不管 "none") |

### 5.2 · 新 regex(实施后确定)

```regex
registered:    ^⟁ Aether · Day \d+/30 · .+? · scope: [^·]+ · handover: day-\d+-handover\.md$
unregistered:  ^⟁ Aether · unregistered · scope: guest @ [^·]+ · handover: none$
```

(实施时发现初稿 `[^·]+` 的分数段正则被 `(32 ok · 2 warn · 3 fail)` 里的内部 `·` 打断 · 改为非贪婪 `.+?` · fixtures 6/6 通过。)

**alternation 安全性**:两个分支互斥 · 不会同时匹配。中间 `[^·]+` 捕获 score 部分(支持 `86/100 (32 ok · 2 warn · 3 fail)` / `?/?` / 未来可能的其他形态)。

**反向测试**:写 4 个 fixture 字符串(S1/S2/S3/S4 各一) · 全部过新 regex · 且 "非法"字符串(比如旧的 `Day 12/30 · 100/100 .* · handover: ...` 缺 `scope:` 段)不过 —— 这有助于校验已部署的旧 status line 真被替换。

### 5.3 · 向后兼容

**旧 status line 字符串不会残留于运行时**(每次 sessionStart 新生成) · 但**历史 coll / handover 里引用旧格式**的文字保持原样 · 不回溯改。coll 是 chronicle(只增不改原则 · 见 `day-11-handover.md` L165)。

---

## §6 · 测试计划

### 6.1 · 手动 4 场景

| # | 测试 | 步骤 | 期望 status line |
|---|---|---|---|
| T1 | dev-self 仍正确 | `cd` 中央 repo · `python aether/bin/aether_handshake.py --test` | `Day 12/30 · 86/100 ...` (不变) |
| T2 | guest + overlay + handover | 在某项目 X 有 `.aether/handover/day-2-handover.md` · `python aether/bin/aether_handshake.py --scope guest --workspace <X>` | `Day 3/30 · ?/? · scope: guest @ X · handover: day-2-handover.md` |
| T3 | guest + overlay + 空 handover | 在项目 X 跑过 `aether project init --apply` 但未写 handover · `--scope guest --workspace <X>` | `Day 1/30 · ?/? · scope: guest @ X · handover: day-0-handover.md` |
| T4 | guest + 未 init | 在某新项目 Y · `--scope guest --workspace <Y>` | `⟁ Aether · unregistered · scope: guest @ Y · handover: none` |

### 6.2 · regex 回归

写一个短 Python 脚本:

```python
import re
PATTERN = r"^⟁ Aether · (Day \d+/30 · [^·]+|unregistered) · scope: [^·]+ · handover: (day-\d+-handover\.md|none)$"

cases = [
    ("S1 dev-self",    "⟁ Aether · Day 12/30 · 86/100 (32 ok · 2 warn · 3 fail) · scope: dev-self · handover: day-11-handover.md", True),
    ("S2 guest+ho",    "⟁ Aether · Day 3/30 · ?/? · scope: guest @ cursor-api-proxy · handover: day-2-handover.md", True),
    ("S3 guest empty", "⟁ Aether · Day 1/30 · ?/? · scope: guest @ demo · handover: day-0-handover.md", True),
    ("S4 unreg",       "⟁ Aether · unregistered · scope: guest @ novel-proj · handover: none", True),
    ("BAD old",        "⟁ Aether · Day 12/30 · 100/100 (31 ok · 0 warn · 0 fail) · handover: day-11-handover.md", False),  # 缺 scope:
    ("BAD missing",    "⟁ Aether · day 12 · scope: dev-self · handover: none", False),
]
for name, s, want in cases:
    got = bool(re.match(PATTERN, s))
    assert got == want, f"{name}: got {got}, want {want} · {s}"
print("regex 6/6 pass")
```

放到 `aether/tests/test_status_line_regex.py`(新文件 · 约 30 行) · selfcheck L11 可选调用。

### 6.3 · 真实 Cursor 回归

1. 重启 Cursor
2. 打开中央 skills repo · 新 chat · 输入 `你好` · 看 AI 第一行 → 应是 S1
3. 打开 `cursor-api-proxy`(或任一其他项目)· 新 chat → 应是 S4
4. `cd cursor-api-proxy && aether project init --apply` → 再新 chat → 应是 S3
5. 在 `cursor-api-proxy/.aether/handover/` 手写 `day-0-handover.md` → 再新 chat → 应是 S2

---

## §7 · Rollback 计划

改动全部集中在 **文件 1-5**(§4.1)· 2 个代码 + 3 个文档 · 无 migration(SQLite / 磁盘格式无变) · **单次 `git revert <commit>` 即可完全回退**。

**特殊注意**:
- RULE 00 regex 是 rules 里的**静态文本** · revert 后旧 regex 回归 · AI 行为立即恢复
- 已写入 guest project 的 overlay(`.aether/`) · 不受 revert 影响(本改动不写磁盘)
- **新创建的 `coll-0092.md` 和 `day-12-handover.md` 是 chronicle** · 即便 revert 代码也建议保留文件(记录讨论过这个问题)

---

## §8 · Out of Scope(本次**不**做的)

以下明确不做 · 避免 scope creep(参考 `docs/WHY-NOT.md` 精神):

1. ❌ **不改 `aether_install.py`** · 装不装 Aether 是 `--global` / `--copy` 的 orthogonal 问题
2. ❌ **不自动 `aether project init`** · sessionStart hook 保持 read-only 契约 · 不写盘
3. ❌ **不实现 overlay 专用 selfcheck**(`--overlay` 模式) · 这是 Day 13 P0 候选 · 本次 guest 评分硬写 `?/?`
4. ❌ **不改 `aether.mdc` 的 5-mode auto-activation 表** · 那和 status line 是正交的
5. ❌ **不回溯改历史 coll / handover 里引用旧 status line 格式的文字** · chronicle 只增不改
6. ❌ **不实现"跨项目 Day 聚合统计"** · 即便有需要 · 那是 `aether_query --global` 的活 · 不在 handshake
7. ❌ **不改 `~/.cursor/rules/aether.mdc`**(全局 rules 副本) · 那是 install 时的镜像 · 由 `aether_install --global --apply` 重装时同步;手动改也行,但不是本次交付

---

## §9 · 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| 新 regex 在某个 AI 实例里没更新(读旧 rules 缓存) | 中 | AI 拒绝贴不符合旧 regex 的 status line | Cursor 下次 session 自动读新 rules · 影响只一 session |
| guest+empty-handover 时 "Day 1" 与 Owner 预期不一致(Owner 可能想 "Day 0") | 低 | 只是字面体感 | 如 Owner 审时要求改 · 统一改 `_latest_local_handover` 返回 → "0" |
| `_latest_local_handover` 对软链 / 奇怪文件名不健壮 | 低 | 异常时 day=None · 落入 S4 分支 | 现 `re.match` 已过滤非法命名 · 异常 path 被跳过 |
| `scope_detail`(项目名)含 `·` 字符 | 极低 | 新 regex 的 `[^·]+` 匹配失败 | `_short_project_name` 本就 clip 到 32 chars · 现实中不会含 `·` |
| 全局 rules(`~/.cursor/rules/aether.mdc`)没同步 | 中 | 全局装的项目继续用旧 regex | 文档 §8 明写 Owner 需重装 `--global --apply` 或手动同步 |

---

## §10 · Owner 审批(请勾选)

**请在下方四选一 · 或写具体修改意见**:

- [ ] **A · approved · 按本文实施** —— AI 立即开工 · 估 60-90 min 完成 · 完后跑 §6.1 T1-T4 + §6.2 regex test · 全绿后生成 commit
- [ ] **B · approved with minor changes** —— 请在下面注明:
  ```
  (Owner 写要改的点)
  ```
- [ ] **C · rejected · 要换方案** —— 请在下面说明哪些地方有异议:
  ```
  (Owner 写异议)
  ```
- [ ] **D · defer to Day 13+** —— 本改动记 task(P0)· 不今天做

---

## §附录 · 设计 RFC 原则(非必读)

本设计遵循的隐性原则(受 linus / rigor field 影响):

1. **向后兼容 > 重构**:dev-self 行为完全不变 · 只在 guest 分支加能力
2. **读写对称**:guest 写 overlay · 读也必须读 overlay · 读写源一致
3. **Single source of truth**:Day N / handover_name 等**有且仅有**三个函数生产 · 其他 .py 禁止自己算
4. **显式优于隐式**:unregistered 时显示 "unregistered" · 不用 fallback 到中央假装有数
5. **fail-open · 不阻塞**:overlay 读失败 → 落 unregistered · 不抛异常 · AI 仍能工作
6. **Owner 控制**:不自动 init 写盘 · unregistered 状态由 Owner 决定是否 `aether project init`
7. **chronicle 只增不改**:历史 coll / handover 里的旧 status line 叙述保留
