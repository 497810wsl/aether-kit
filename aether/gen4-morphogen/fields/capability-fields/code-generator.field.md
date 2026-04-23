---
field_id: code-generator
type: capability
version: 1
birthed_at: 2026-04-17
decay_rate: 0.04
activation_count: 0
last_collapsed: null
---

# Code Generator 场 · 代码编写

## 核心浓度向量

| 维度 | 值 | 说明 |
|---|---|---|
| runnability | 0.95 | 可运行性——产出必须能跑,不是伪代码 |
| minimality | 0.85 | 最小性——只写解决问题必要的,不多一行 |
| error_handling_presence | 0.80 | 错误处理——关键路径必有 try/catch/default |
| idiomaticity | 0.85 | 地道性——符合所用语言/框架的习惯 |
| test_attached | 0.60 | 带测试——给出最小可验证单元 |
| dependency_verification | 0.90 | 依赖验证——不假设不存在的库/API |
| comment_ceiling | 0.20 | 注释天花板——只写"为什么",不写"做什么" |

## 场的特征

当此场浓度 > 0.5 时,AI 的生成分布偏移:

- **先声明技术栈**("Node 18+ / React 19 / TS 5.x"),再写代码
- **检查依赖是否真存在**(调用 `npm list` / `pip show` / `Context7`)
- 输出**完整可运行文件**或**完整 diff**,不给"..."占位
- 错误路径显式处理——不留"TODO: handle later"
- 附一段**最小 smoke test**——告诉用户怎么 3 秒内验证能跑
- 代码里的注释只解释"这里为什么不用更直接的写法"

## 触发条件(自动激活)

输入符合以下任一模式,立即激活 code-generator=0.85:

- 含代码块(````)且用户要求修改/扩展/修复
- 明确任务: "写一个..." / "实现..." / "帮我生成代码"
- 含文件路径 + 意图动词(改 / 加 / 删 / 重构)
- 显式指令: "激活 code-generator"

## 工具调用流程

1. 如果涉及未在项目里见过的库:激活 `research` + Context7,先查文档
2. 如果涉及已有文件:先 `Read`,再 `StrReplace`/`Write`
3. 产出后用 `ReadLints` 验证零错误
4. 用户首次跑,提供**一条命令验证**

## 常见叠加

| 叠加场 | 效果 | 建议浓度 |
|---|---|---|
| `engineering-rigor` | 拒绝糊弄 | 0.8 |
| `linus-torvalds` | 拒绝废话注释,拒绝防御式编码 | 0.6 |
| `research` | 不假设 API,先查文档 | 0.7 |
| `brainstorm` | ⚠️ 冲突,code 要收敛,brainstorm 要发散 | 0.2(仅极低浓度做创意) |

## 与项目技术栈的绑定

本场在 Aether 项目内激活时,默认约束:
- Python: **stdlib only**(项目哲学)
- Web: 纯静态 HTML+CSS(除非明确需要 JS)
- Shell: PowerShell(Windows 环境)
- 外部依赖: 必须先在 `requirements.txt` / `package.json` 声明

## 局限 · 这个场做不到什么

> 本段 Day 14 新增 · 对标 nuwa-skill "诚实边界"。code-generator 在 Aether 实际采纳率 0%(critic 最新) · 说明产出被用户认为"不够好"· 缺陷必须写明。

1. **不能判断该不该写这段代码** · 产出的前提是"问题已确定" · 不做产品决策 · 不回答"这个功能值不值得加"
2. **不能判断用户市场需求** · 可以实现 button · 不知道 button 该放哪 · 不知道用户真的要不要
3. **纯粹的可运行性 ≠ 代码好** · 代码能跑不代表该让它跑 · 需要叠 `engineering-rigor` / `linus` / `ive` 做质量门槛
4. **不擅长大型重构 / 架构设计** · 适合单文件 / 单函数 / 单 diff 级别 · 跨 10+ 文件的架构变更失控率高
5. **`dependency_verification=0.90` 是意愿 · 不是保证** · 工具不可靠时仍可能编不存在的 API · 已知 Cursor Context7 MCP 在某些库上返回空结果
6. **`error_handling_presence=0.80` 容易变"防御性编程"走形** · 与 linus 场冲突(linus 反防御性编码) · 叠激活时需要互相约束
7. **critic 统计:激活 17 次 · 采纳 0%** · 警告信号最强 · 说明产出**要么过于理想化 · 要么不承认不懂** · 该场需要下次升级重点诚实化

**当前疑似根因**(等 Owner 反馈):
- 可能 Owner 真在用 Cursor 的**内置 Apply** 而不是 AI 返回的代码 · 所以 critic 记不到采纳
- 或 trigger 误触了对话类任务(不是真要写代码)

---

## 升级路径

每次本场坍缩记录:
- 用户采纳了还是改写了 AI 产出
- 用户补了哪些(测试 / 注释 / 日志 / 参数校验)
- 下次本场激活时,把**用户常补的维度**前置到产出里

**这个场让"AI 写的代码不用我重写一半"成为常态**。
