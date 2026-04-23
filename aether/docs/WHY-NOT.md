# Aether · WHY-NOT 清单

> 起草于 Day 11(2026-04-22) · Owner reality-check 后 · 防 scope creep。
> **此文档的目的**:当 Day N AI 实例或 Owner 冒出"加一个 X"冲动时 · 先读这里。
> 每条 NOT 都带**具体理由** · 不是品味 · 不是"以后再说"。

---

## 这个文档的使用方法

**触发条件**(任一):
1. 你想**加新 CLI**(`aether_*.py`)
2. 你想**加新 hook 事件**
3. 你想**加新 gen 世代概念**(gen8 / gen9 / ...)
4. 你想**加新 field**(超出现有 20 个)
5. 你想**写新哲学 / 本体论 / 诗化命名**
6. 你想**"重构" 已有真资产 4 文件**(handshake / hook / paths / install)

**做法**:先读本文对应 NOT 条款 · 如果仍然要做 · 在 coll 里明确反驳本文的理由。**不反驳就别做**。

---

## NOT-1 · 不加新 aether_*.py CLI(当前 29 个已过量)

**理由**:
- 29 个 CLI 中 · 13 个使用频次 ≤ 月级(详见 coll-0090 L5 假逻辑)
- 单用户系统 CLI 数量 = **防御机制** · 每多 1 个 = 每多 1 层"我还在工作"证据 = 多 1 个"系统已完备不急发布"借口
- Day 9 已承诺"不加新 CLI" · 本文再加固

**例外**(唯一):Owner 选定形态 α/β/γ 后 · 主动精简到 ≤ 10 个 · 是**减** 不是加。

**信号**:你想写 `aether_new_thing.py` 时 · 先问:
1. 29 个里哪个 CLI 能扩展一个 subcommand 就覆盖?
2. 这个功能是 `aether_hook.py` 某个 event 的 handler 就行吗?
3. 形态选了没?选了的话砍 19 个 CLI 先行 · 再谈加。

---

## NOT-2 · 不加新 Cursor hook 事件(9 个已覆盖 Windows 实际可用的全部)

**理由**:
- `.cursor/hooks.json` 9 events 已覆盖 6 个**真有 payload**(sessionStart / sessionEnd / postToolUse / preCompact / agentResponse / beforeShellExecution)
- 剩下 9 个"官方 events" 多数在 Windows 上是空 payload(Anthropic GH #48009 · coll-0067)· 加了也只是 `cursor-empty` 垃圾
- Day 9 已承诺"不加新 hook"
- **50% 覆盖率**(9/18)是虚荣指标 · 实际 100% 的"有效 events"

**例外**:Cursor 本身发新版本修了 Windows payload bug · 且新 event 有 payload · 才考虑。

---

## NOT-3 · 不加新 gen 世代目录(gen8 / gen9 / ...)

**理由**:
- gen5-ecoware 物种层: 1 物种 10 天 · 0 涌现(HON "species diversity fail")
- gen6-noesis coll: 100% 自我指涉(HON "coll self-ref rate fail")
- gen7-logos: 占位符 · 已在 Day 11 诚实化
- **再加 gen8 = 第 8 个装潢**(coll-0090 根因 2 · 哲学语言包装工程债)
- 当前 4 个世代**没一个形成真 emergence** · 再加只会让"装潢分 93 / 诚实分 78"差距更大

**例外**:`labs/archive-concepts/` 不是 gen-N · 是归档路径 · 可以有。

---

## NOT-4 · 不加新 field(当前 20 个已过量)

**理由**:
- 9 active(gen4)+ 9 dormant(labs)+ 2 pro = 20
- 3 核心 field 有证据列 + `.test.md`(rigor / linus / ive) · 另 17 个都是"写出来但没证据"
- Day 11 reality-check "14 假逻辑"之一:大量 field 没被采纳率统计证明有用
- 先给现有 17 个写证据列(Day 10 handover P0 清单)· 再谈加新

**例外**:若已完成全部 17 个证据列验证 · 且发现真有缺口 · 才加。**不会在 Day 30 前发生**。

---

## NOT-5 · 不加新哲学 / 本体论 / 诗化命名

**理由**:
- "场 / 物种 / 坍缩 / 共振 / morphogen / noesis / logos" 已经够了
- 新术语 = 新内部通讯协议 = 新学习成本 = 新"AI 看起来智能 Owner 看起来博学"的 vanity
- Day 1 的 `reality-check-gen1.md` 诊断 "元概念绑架" · Day 11 复盘确认 **10 天 0 改善**
- Day 11 已把 `ONE.md` 从"诗化条件"改成"可审计硬指标" · 方向明确

**例外**:新术语能 **替代** 一个旧术语(一对一替换 · 净值 0 增长) · 且旧术语被 Owner 投诉难用。

---

## NOT-6 · 不重构 4 个真资产文件(除非 Owner 显式命令)

**4 个真资产**(coll-0090 证实):
- `aether/bin/aether_handshake.py`
- `aether/bin/aether_hook.py`
- `aether/bin/aether_paths.py`
- `aether/bin/aether_install.py`

**理由**:
- 这 4 个是 Aether 对 Owner 日常工作**唯一有价值**的部分
- 运行 10+ 天 0 回归 · 本身是稳定成果
- "重构"这些 = 动核心 = 高破坏风险 · 收益不明
- Day 9-10 的"overlay-aware 迁移"之所以 OK · 是因为那是**加**能力(scope 分派)· 不是**改**核心逻辑

**例外**:发现真 bug(如 Day 10 字典序)· 改动局限于 ≤ 10 行 diff + 有回滚路径 · 且先写 coll 说明。

---

## NOT-7 · 不自动化 "跑 selfcheck fix"(即使 `--fix` flag 建议)

**理由**:
- `aether_selfcheck.py --fix` 的注释是 "(future) auto-fix safe issues"
- "safe issues" 的定义权应该在 Owner · 不在 AI
- 自动修会让 Day N+1 的 AI 实例无法追溯"Day N 为什么改了这个"
- Day 10 session 5 的 bug 发现路径(Owner 追问 → AI 挖算法)· 在 auto-fix 场景下**不会发生**

**例外**:`--fix` 只 auto-fix **文件存在性类**问题(创建缺失目录 / 初始化空 jsonl) · 不 auto-fix **语义类**问题。

---

## NOT-8 · 不在 30 天窗口内做"形态 δ"(α/β/γ 之外)

**理由**:
- Day 11 分析已枚举 3 种可能形态 · 覆盖 65% + 25% + 10% = 100% 概率
- "形态 δ"(例如"开源 + 投资 + 社交平台")= 3 种都 reject 的幻想
- 30 天内能落地 = 先 focus 一种 · 而不是发明第 4 种

**例外**:Owner 在 Day 12+ 显式说"我不要 α/β/γ · 我要 δ" · 那时再评估。

---

## NOT-9 · 不写新的"launch 文案"(Day 15 前)

**理由**:
- `launch-copy-draft.md`(Day 3)· `launch-copy-v2.md`(Day 4)· `pro-tier-gumroad-draft.md`(Day 3)· 都在 `labs/chronicle/`
- Day 15 HN launch 前需要的是**修改这些**(特别 v2 · 加入 Day 6 infrastructure + Day 10 ep-0002 + Day 11 reality-check 叙事)
- 再写 v3 = 又一份 draft · 不如直接改 v2

**例外**:Owner 选形态 α/γ 之一 · 旧文案无法复用 · 才写 v3。

---

## NOT-10 · 不做"外部 AI 实例 review"之前的营销动作

**理由**:
- launch-copy-v2 依赖"staff-engineer 场外部验证" + "stats 实时数字" 两个硬锚
- 当前 stats 已刷新(Day 11 P0-2) · 但"外部验证"仍然**只有 1 次**(coll-0065 · Day 3)
- Day 15 launch 前 · 至少再跑 2 次外部验证(用不同 AI 实例 / 或找 1 个陌生人做 5 分钟测试)
- 没有外部验证 · 所有"我用我自己工具改变了我自己决策" 的叙事容易被 HN 挑出"self-referential"

---

## 当前已知"未兑现的承诺"(chronicle 留痕)

> 这些是 Day 1-10 写下但 Day 11 确认未做的承诺 · 保留不删 · 用于决策参考。

| 承诺 | 位置 | 未做度 | Day 11 处置 |
|---|---|---|---|
| "7 天真实使用实验" | `reality-check-gen1.md` §反转方向 | ❌ 0% | append Day 11 复盘 · 不删 |
| "5 个真实外部用户" | 同上 | ❌ 0% | 同上 |
| "系统精简 60%" | 同上 | ❌ -164%(反方向) | 同上 · 等形态决策 |
| ep-0001 15 维度剪建议 | `ep-0001.md` | 0/15 | Day 11 ep-0003 supersede · 声明不采纳 |
| "Pro field 5 个起步" | launch-copy-v2 | 2/5 | 未处理 · Day 12+ 形态 β 时扩 |
| "StrReplace post-edit checksum"(task-0030) | `.aether/tasks.jsonl` | 未做 | 2 天 stale · Day 12+ P1 |

---

## 这个文档本身的 NOT-11

**NOT-11 · 不扩展本 WHY-NOT 超过 15 条**

**理由**:
- 超过 15 条 · AI / Owner 记不住 · 反而失效
- 真正关键的 5-10 条刚好
- 当前 10 条已经覆盖了 coll-0090 14 假逻辑的**根因**部分

**例外**:某条 NOT 被证明失效(Owner 显式允许例外 3 次)· 再 revise。

---

*此文档是 chronicle · 只增不改。Day 12+ 如需更新 · 在末尾 append "## Day N 追加" 段 · 不修改上文条款。*

*最后更新:Day 11 · 2026-04-22 · AI 在 Owner "继续推进" 授权下起草。*

---

## Day 12 追加(2026-04-22) · 三次 reality-check 后

### NOT-12 · 不追求"颠覆 senior 前后端 app"

**理由**:
- Christensen 颠覆标准需要:团队 + 多年 + 10x 某维 + 独立平台。Aether 四项全无
- 数学估算:对 senior 前端颠覆 <2% · 后端 <1% · app <1% · 三者相乘 ≈ 0.0002%
- 30 天内达成平台级颠覆 = **0%**(历史 0 例 · 最短 Docker 用 5 年 + 融资)
- Aether 依赖 Cursor · 一旦 Cursor ship 原生跨会话记忆 · 核心 value 蒸发(platform risk)
- Owner 在 Day 12 session · 被 AI 明确告知此概率后 · 主动说"**愿意继续**" · 说明**已接受非颠覆**为最高目标

**Owner Day 12 亲定的新成功标准**:
- **1 个不认识 Owner 的 dev 在 GitHub star 项目** · 或
- **5 人被手动邀请试用** · 两者择一达成 = Day 30 赢

**例外**:无。颠覆不是"以后可以加上"的目标 · 是**数学证明不可及的目标** · 除非 Aether 变成 Cursor 级的公司 / 团队 · 那时本文自动失效。

**详情**:`aether/labs/chronicle/scope-reaffirmation-2026-04-22.md`(本日决定的 full record · 包含 3 次 reality-check 链条 / Owner 答复原话 / 4 件锁定事 / 给未来的 guardrail)。

---

*Day 12 追加结束。下次追加 · 在本段之下再加 "## Day N 追加" · 不改上文。*
