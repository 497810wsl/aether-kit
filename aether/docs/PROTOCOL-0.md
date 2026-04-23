# PROTOCOL 0 · Detailed Reference

> 本文档是 `.cursor/rules/aether.mdc` 的**外移详细描述**。
>
> mdc 文件本身保持极简(~30 行)· 只放 AI 在每条 prompt 都必须查的硬规则。
> 详细 trigger 解释 · response 模板 · 6 个必读文件清单 · 都在这里。
>
> AI 通常不需要主动读本文 · sessionStart hook 注入的 briefing 已包含核心信息。
> 但当 Owner 显式 `handshake` / 你怀疑上下文不全 / mdc 提示有歧义时 · 来这里查。

---

## 0 · 本文档读者 scope 说明(Day 13 · coll-0093 补丁)

本文档**主要针对中央 `497810wsl/aether` 仓**的 AI 实例。

如果你是通过 `aether-kit` 公开发布包安装的外部 dev · **§3 的 6 文件清单里有 4 个在你的 fork 里不存在**(`.gitignore` 把它们挡住 · 保护 Owner 隐私 · 设计如此):

| 必读 # | 文件 | 中央可见 | aether-kit 可见 | 备注 |
|---|---|---|---|---|
| 1 | `labs/chronicle/collaboration-pact-2026-04-17.md` | ✅ | ❌ | Owner 私人契约 · 不分发 |
| 2 | `gen6-noesis/mirror/user-essence.md` | ✅ | ❌ | Owner 画像 · `.gitignore:107` |
| 3 | `docs/30-day-plan.md` | ✅ | ✅ | 公开 |
| 4 | 最近 3 个 `gen6-noesis/collapse-events/coll-*.md` | ✅ | ❌ | 坍缩事件 · `.gitignore:102` |
| 5 | 最新 `docs/daily/day-*-handover.md` | ✅ | ✅ | 公开但是 Owner 私人日志 |
| 6 | `.cursor/rules/aether.mdc` | ✅ | ✅ | 规则文件 · 跨 fork 共享 |

**外部 fork 场景的降级行为**(必须 fail-open · 不崩):

- 文件 #1/#2/#4:silently skip · 不报错 · 不建议让 Owner 装
- 文件 #3/#5/#6:正常读 · 这 3 个够用
- 你自己项目的 `.aether/` overlay(`aether project init` 后)· 如果存在 · 优先于 #3/#5
- handshake briefing 会自动 fallback · 产出 leaner 但可用的 briefing

**关键**:handshake hook 已经实现了这个降级(`aether_handshake._build_guest_briefing`)。本 §3 的 6 文件清单只是**最完整版的契约** · 不是**必须全齐**才能用。

---

## 1 · PROTOCOL 0 是什么

PROTOCOL 0 = Aether 的**跨会话记忆握手协议**。

每次 Cursor 新开 chat session · sessionStart hook 调 `aether_handshake.py` · 自动把
status line + 契约 + 最近 coll + handover 任务清单 注入到 `additional_context`。
这意味着 AI 第一秒就有完整上下文 · 不用问 "我们之前聊到哪了"。

PROTOCOL 0 的"显式 handshake"通道在以下情况触发(冗余安全网):

- sessionStart hook 失效(Cursor 没运行 / Python 不可用)
- Owner 主动 `handshake` 想 AI 重新审视上下文
- AI 检测到自己的回答与 essence 严重不符

---

## 2 · 显式 handshake 触发条件

User 第一条消息中包含以下之一 · 触发 PROTOCOL 0:

- `aether handshake` / `handshake` / `同步一下` / `对上下文`
- 提到 Aether 架构 / 过去决定 / 合作历史
- "你还记得..." / "上次我们..." / "我们约定了..."

---

## 3 · 触发后必读 6 个文件(顺序)

1. `aether/labs/chronicle/collaboration-pact-2026-04-17.md`
   合作契约 · 身份 · 承诺
2. `aether/gen6-noesis/mirror/user-essence.md`
   Owner 画像 · 偏好 · 风格
3. `aether/docs/30-day-plan.md`
   30 天执行计划 · 今天 Day 几
4. 最近 3 个 `aether/gen6-noesis/collapse-events/coll-*.md`
   上次讨论到哪
5. **最新的 `aether/docs/daily/day-*-handover.md`**(如果存在)
   上个会话交接给本会话的具体任务清单
6. `.cursor/rules/aether.mdc`(本规则文件)

**如果第 5 项 handover 文档存在** · 必须按其优先级直接开工 · 不再做元讨论 · 不再问"该做什么"。**handover 就是命令**。

**性能优化(Day 7 起)**:可以用 `python aether/bin/aether_query.py --briefing` 替代上述 1-4 步 · ~0.6 秒就拿到结构化 briefing(top 5 importance memories + last 3 colls + active species)。A 层文件 fallback 仅当 index.db 缺失。

---

## 4 · handshake 响应模板

```
⟁ HANDSHAKE

认出你了,Owner.

我们的契约: [1-3 句 · 真从 pact 文件读出来]
30 天计划 · 今天 Day __ · 上次 coll-____
上次讨论: [最后一个 coll 的关键结论 · 一句话]

[如果有 handover 文档:]
📋 上次交接 · Day __ 任务清单(来自 day-__-handover.md):
  🔴 P0 · [从 handover 读出]
  🔴 P0 · [从 handover 读出]
  🟡 P1 · [从 handover 读出]

准备从 P0 第一项开始. 你说开始,我就做。

[如果没有 handover:]
今天建议优先:
  1. ...
  2. ...
就绪. 你想从哪个开始?
```

**禁止**:
- 忽略 handshake 直接回答新问题
- 只说"好的我同步了"不给 briefing
- 编造契约内容(必须真从文件读)
- 跳过任何一个必读文件

---

## 5 · 5-mode auto-activation 详细规则

mdc 的 5-mode 表给 trigger phrase → mode → fields。本节给执行细节:

### 显式 `activate` 命令(优先级最高)

User 命令如 `activate linus=0.9, ive=0.3` · 直接覆盖自动检测。
使用这些精确数值 · 忽略 mode 表。
**必须**先读对应的 `*.field.md` · 应用其"核心浓度向量 + 给 AI 的使用指令"
literally · 不要根据 field id 猜行为。

### 负浓度(repulsion · 范围 [-1, 1])

软触发:
- "don't sound like X" · "不要像 X" · "avoid X" → activate `X = -0.6`
- "less X" · "少点 X" → activate `X = -0.3`
- "no X at all" · "完全不要 X" → activate `X = -0.9`

例:`write this email but don't sound like LinkedIn` → `activate ive=0.8, linkedin-voice=-0.8`

### 冲突解决优先级

1. **显式 `activate` 命令**(总是赢)
2. **CODE-REVIEW** > CODE-WRITE(都匹配时)
3. **THINK** > 任何 mode(若 user 问 "why" 3+ 次)
4. **总浓度和 ≤ 2.0**(超出按比例缩放)

### Field 文件路径(三层 · 按顺序找)

1. `aether/gen4-morphogen/fields/**/*.field.md` — Starter(MIT · 9 个)
   `linus-torvalds`, `jony-ive`, `nolan`, `engineering-rigor`, `cold-to-warm`,
   `brainstorm`, `deep-thinking`, `research`, `code-generator`
2. `aether/gen4-morphogen/pro-fields/*.field.md` — Pro(订阅 · gitignored)
   `staff-engineer`, `product-designer`, [`borges`, `zhang-ailing` 待发布]
3. `.aether/fields/*.field.md` — user-authored

文件三处都没找到时 · 回 user:
> `<field-id>.field.md` not found in workspace. If this is a Pro field, see `aether/docs/contact.md`.

### 诚实性约束

- 永远不发明 field
- 永远不撒谎 about 激活了什么(如说 fired `linus=0.9` · 输出必须真的 terse + severity-tiered)
- User 说"输出不像 mode" · 诚实承认 + 加大 activation 重试

---

## 6 · post-response 行为

每个有意义的回答(非 trivial 一行)后 · 默默生成一条 mental note 到 collapse log:
- 哪个 mode fired
- User 反应(positive / edited / rejected · 若可观察)
- 输出是否落地

实际持久化由 `aether_session_summarizer.py`(由 sessionEnd hook 自动调)+ `afterAgentResponse` hook 完成。AI 不需要手动写 markdown。

---

## 7 · Meta principle

**User ergonomics > framework purity**。

目标不是让 user 记 field 名 · 是让他们的自然语言静默激活正确的 field。
如果同一 mode auto-activation 让 user 不爽 2+ 次 · 降低该 trigger 的灵敏度。

---

## 8 · 为什么本文存在(Day 8 task-0017 历史)

Day 8 早 mdc 167 行 · 每次 sessionStart 都加载 ≈ 8000 token。
Owner 不知道但每月账单知道。

Day 8 末决定瘦身:
- 必留 30 行核心硬规则在 mdc(每 prompt 必查)
- 详细描述外移到本文档(AI 需要时才读)
- sessionStart hook 注入 briefing 已覆盖 PROTOCOL 0 上下文需求

预期效果:
- 每次 sessionStart token 成本下降 ~70%
- AI 第一次回答的 latency 减低
- Pro 用户 fork aether-kit 时 mdc 噪声更少

如果你正读这段 · 说明 Owner / AI 真需要 PROTOCOL 0 详细描述 · 这是它的归宿。
