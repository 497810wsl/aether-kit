# Aether 30 天执行计划 · 2026-04-17 起

> 详见合作契约: `labs/chronicle/collaboration-pact-2026-04-17.md`
> 本文件是 Owner 和 AI 共同执行的日级任务清单。
> 每天完成一项 · 打 ✅ · 不完成记录原因。
>
> **Day 12+ · 成功标准以 `labs/chronicle/scope-reaffirmation-2026-04-22.md` 为准**。
> 本文 Day 22-30 的旧 kill criteria("≥ 50 stars / ≥ 1 付费 / ≥ 3 陌生反馈")**已被 Owner 亲签的新标准覆盖**:
> **"1 个不认识 Owner 的 dev star 项目 · 或 5 人手动邀请试用 · 择一即赢"**。
> 本文 Day 22-30 部分保留为历史叙事 · 不再作为决策依据。

---

## 总进度条

> **Day 11 修正**(Owner reality-check 触发 · AGENTS §3.7 Day N 硬约束):
> 进度条曾经写"6/30 days" · 静态不更新 · 和真实 Day N 脱钩。
> **权威来源 = `docs/daily/day-N-handover.md` 的最大 N + 1** · 由 `aether_handshake.current_day()` 计算 · 注入 status line。
> 本文件不再维护数字进度条 · 防双份 SOT。

Current Day = 参见 sessionStart 注入的 status line(`⟁ Aether · Day N/30 · ...`)· 或跑:

```bash
python aether/bin/aether_handshake.py --test
# 或
ls aether/docs/daily/day-*-handover.md | sort -V | tail -1
```

Week 分段(按 Day 算):Week 1(Day 1-7)· Week 2(Day 8-14)· Week 3(Day 15-21)· Week 4(Day 22-30)。

**Day 3 硬事件**:
- Pro 策略 pivot 成 WeChat + GitHub 直连(Gumroad 降级为后备)
- `staff-engineer.field.md` v1 · 外部 AI 实例验证通过(coll-0065)
- Owner 用自己产品否决"加登录平台 pivot"冲动 · pact 自洽

**Day 4 硬事件**(2026-04-18 · 实际走偏原计划):
- 触发: Owner 一句"我公开的内容是否有我的核心数据呢"
- 隐私审计: aether-kit 33 文件 / aether 全历史 / 两 repo fork 状态全扫 · 0 泄漏
- 大重构 1: `aether/` workspace 顶层 25 → 7 项 · root 变 thin pointer (commit `b7949ca`)
- 大重构 2: `aether-kit` 公开仓库顶层 11 → 5 项 · v0.4.2-kit (commit `a68e0a8`)
- 自检 CLI 修复: `selfcheck` / `integrity` / `snapshot` 三件套 ROOT 锚点拆分 · 健康分 78 → **100/100** (commits `f62bf9e` + 本日末)
- gitignore 哑弹排雷: 460KB 私密快照 zip 未被忽略 · 修
- Day 4 handover: `docs/daily/day-4-handover.md` 写入 · 含 Day 5 完整 P0/P1/P2 清单

**Day 5 硬事件**(2026-04-19 凌晨 · 还 Day 3 旧债):
- 三个 P0 债一次清完: docs/index.html + manifesto.html + 2 CSS · -1084 行 · GitHub Pages 路线废弃
- 7 个 stale `aether-kit` URL 补 `kit/` 前缀(post-restructure 副作用)
- deploy.ps1 pem 路径 bug 修复(另一颗哑弹)
- coll-0066(Day 4-5 意义层捕捉)+ Day 5 handover 写入
- 健康分守住 100/100

**Day 6 硬事件**(2026-04-19 · Week 1 最重的一天 · 18 commits + v0.4.3-kit):
- 早段 P0.1: user-essence drift HIGH → LOW · 一次修复跨 2 级(commit `05bbc01`)
- 中段 P2.2: critic Format B + field aliases + canonical coll template · 60 coll 全解析(commit `84ddfe5`)
- 中段 P2.3: Week 1 retrospective 起草(commit `7b8b0d9`)
- 下半段触发: Owner "Cursor 里有 hooks 啊" · 重写 Week 2 方向
- sessionStart hook 系列: PROTOCOL 0 compile-time(commits `69fef7c..447d18a` 5 个)
- 跨平台重构: PowerShell wrapper 删 · 单 Python 入口(commit `6a64d19`)
- beforeSubmitPrompt 死路探索: Cursor 不接受 updated_input · Anthropic GitHub #48009 Windows stdin bug · pivot 回 sessionStart only(commits `f691e43` + `9a0bff9`)
- v0.4.3-kit 上线: install-hook.{ps1,sh} 全平台 · global dispatcher · Aether 第一次有可分发 infrastructure(commit `da5f0f4`)
- coll-0067 + coll-0068 + Day 6 handover 闭环
- 健康分全程 100/100 · selfcheck 0 fail / 0 warn

**Day 6 末状态**: aether-kit v0.4.3-kit · 任何 Cursor 用户 git clone + install-hook + 重启 = 全局 PROTOCOL 0 能力 · 非 Aether workspace 零影响。

---

## Week 1 · Foundation(Day 1-7)· 定位清洗 + 扩展启动

### Day 1 · 2026-04-17(今天 · 已完成)

- 签合作契约
- 写记忆持久化系统(pact + plan + handshake 协议)
- 更新 user-essence
- 写 coll-0059 记录今日决策

### Day 2 · 2026-04-18 · ✅ 完成(coll-0063)

**按 handover(`docs/daily/day-2-handover.md`)执行 · 和 30 天计划原列任务有偏移 · 实际按"先跑通再扩展"原则优先**

实际完成(AI · 1 次 agentic run):

- README.md 覆盖重写(EN · 首屏按 Q1)
- README.zh.md 首次创建(本地化非翻译)
- Features.astro 3 卡 vs `.cursorrules` 重构 · i18n 同步
- Compare 页加强 · 3 新 section 中英同步
- Pricing 页文案收敛到个人工程师
- GitHub repo description + 20 topics + homepage 更新
- 3 轮 deploy.ps1 · 全部 HTTP 200 验证
- coll-0063 + day-3-handover.md

原列但推迟:

- VS Code 扩展脚手架 —— 推迟(pact 明确"先跑通再扩展")
- GitHub Day 2-30 daily issues —— 推迟(减法原则 · handover 已是更好的任务载体)
- Owner 跑 aether-start.ps1 —— 未验证(Owner 端任务)

### Day 3 · 2026-04-19 · ✅ 完成(coll-0064/0065)

实际(与原 plan 偏离 · VS Code 扩展路线**已搁置** · pivot 为 Pro 策略 + 站点收口):
- Pro 策略 pivot 成 WeChat + GitHub 直连
- `staff-engineer.field.md` v1 落地
- Pro pricing CTA 从 Gumroad 改回 WeChat 直连
- 外部 AI 实例验证 staff-engineer 输出质量
- 自我否决"加登录平台"冲动

### Day 4 · 2026-04-20 · ✅ 完成(详见 `docs/daily/day-4-handover.md`)

实际(与原 plan 完全偏离 · VS Code 扩展未做 · 转入隐私审计 + 工程加固):
- 全仓库隐私审计 · 0 公开泄漏证实
- workspace 大重构 · root 25→7 项
- aether-kit 公开仓库重构 · root 11→5 项 · v0.4.2-kit
- 自检 CLI 三件套 ROOT 锚点修复 · 健康分 78→100/100
- gitignore 漏洞补丁 · 私密快照不再裸奔

### Day 5 · 2026-04-19 凌晨 · ✅ 完成(详见 `docs/daily/day-5-handover.md`)

实际(还 Day 3 旧债):
- 三个跳过两次的 P0 债一次清完(docs/index.html + manifesto.html delete · -1084 行)
- 7 stale `aether-kit/blob/main/docs/` URL 补 `kit/` 前缀
- deploy.ps1 pem 路径 bug(post-restructure 哑弹)
- stats.json 真实性核对(handover 数字写错 · 真相一开始就准)
- Day 5 handover 写入 · queue Day 6 P0.1(mirror essence 修复)

### Day 6 · 2026-04-19 · ✅ 完成(详见 `docs/daily/day-6-handover.md` + coll-0067/0068)

实际(Week 1 最重的一天 · 18 commits aether private + 1 commit v0.4.3-kit public):
- 早:mirror drift HIGH → LOW · critic Format B + 别名合并 · Week 1 retro 起草
- 下半:**hook 化 8 commits 演化** · sessionStart auto-handshake · PowerShell → Python 跨平台 · RULE 00 强化
- 末:beforeSubmitPrompt **死路探索 + pivot**(Cursor 不支持 updated_input · Anthropic #48009 Windows stdin bug)
- 真夜:**aether-kit v0.4.3-kit 上线** · install-hook 全平台 · global dispatcher · Aether 第一次有可分发 infrastructure
- 健康分全程 **100/100** · 0 fail / 0 warn 全天
- 5 个错误假设 + 5 次纠错 · 由 selfcheck/critic/web 搜索/Cursor 文档 fetch 驱动 · 方法论入档

**Day 6 重点**: Aether 从"workspace tool" → "Cursor infrastructure"的跃迁日。

### Day 7 · 2026-04-19/20 · ⏳ 待开工 · Week 1 最后一天 · 复盘日

P0(详见 `docs/daily/day-6-handover.md`):
- **P0.1** Review + 修订 `labs/chronicle/week-1-retro.md`(45 分钟)
  - 加 Day 6 下半 infrastructure 跃迁段落
  - 重写 Week 2 方向(原 A/B/C/D · 现 D 已实质启动 · 该重新定义 sub-tasks)
  - 加 Owner 视角注解
  - ROI 分析
- **P0.2** 30-day-plan.md 同步 Day 7 决策点(15 分钟 · 等 P0.1)
- **P0.3** 写 coll-0069 记录复盘决策(retro 完成后)

P1(可选):
- 跑 critic / calibrate 看 60+ coll 数据
- 写 `cursor-hooks-findings.md` 公开技术博客(launch 素材)

P2:
- `product-designer.field.md` v1(Pro 场 #2)

### Day 7 · 2026-04-23

Owner 任务:

- Week 1 复盘: 扩展能不能用?网站够不够清楚?
- 决定 Week 2 的重点

AI 任务:

- 产出 `labs/chronicle/week-1-retro.md` 复盘报告

---

## Week 2 · Product(Day 8-14)· 扩展完成 + 上架

### Day 8-10 · 扩展最后冲刺

- 扩展的 5 模式按钮 UI polish
- 图标 · 截图 · 动图
- VS Code Marketplace 上架材料
- Cursor Extensions 上架(如 Cursor 开放)

### Day 11-13 · 推广素材

- HN Show HN 文案最终版
- Twitter 10 条 thread
- Dev.to 英文博文
- 知乎 / 掘金 / V2EX 三份中文稿
- OG 图 · 演示 GIF · 微信朋友圈图

### Day 14 · 预推广小范围测试

- 微信找 5 个朋友试用 · 收 5 条反馈
- Week 2 复盘

---

## Week 3 · Launch(Day 15-21)· 第一波推广

### Day 15 · 周二

- HN Show HN · 提交 + 首评(时间: 北京 11 PM / PT 8 AM)
- Twitter thread · tweet 1 发(带 OG 图)

### Day 16 · 周三

- Dev.to 英文长文
- Twitter thread · 补发 tweet 2-5

### Day 17 · 周四

- 知乎 + 掘金 中文长文
- Twitter thread · 补发 tweet 6-10

### Day 18 · 周五

- V2EX 分享创造帖
- Reddit r/programming 或 r/MachineLearning

### Day 19-20 · 周末复盘 + 调整

- 看各平台数据
- 回复每条评论(算法权重)
- 写一篇"数据 24h 复盘"推文

### Day 21 · Week 3 复盘

- 第一周总 exposure · stars · installs · signups

---

## Week 4 · Traction(Day 22-30)· 变现 + 社区

### Day 22-24 · 付费场包

- 上架 3 个 Gumroad 场包
- 支付流程测试
- landing page 加 Pricing

### Day 25-27 · 社区化

- 开 Discord 或微信群
- 回复所有 GitHub issue
- 写第二篇博客 "7 天复盘"

### Day 28-29 · 准备盘点

- 收集所有 metrics
- 列出已完成和未完成
- 诚实评估

### Day 30 · 2026-05-17 · FINAL DECISION

用合作契约第六节的标准评判:

- GitHub stars ≥ 50? 
- 付费用户 ≥ 1?
- 陌生人反馈 ≥ 3 条?

根据结果 · 选择:

- **全部达到期望** → 全职 · 招人 · 进入 60 天阶段
- **达到最低** → 半全职 · 继续做 · 但不辞职
- **未达最低** → 按 pact 归档 · 投入下一个项目

---

## 每日模板(Day 2 开始每天贴这个)

```
## Day N · YYYY-MM-DD

Owner 时间投入: ___ 分钟
今日完成:
  - [x] ...
今日未完成(原因):
  - [ ] ... (reason)
发现的问题:
  - ...
明日重点:
  - ...
```

---

## 停止条件 · 不等到 Day 30 就放弃的场景

以下任何一项发生,立即暂停计划重新评估:

1. **连续 3 天 Owner 投入 0 分钟** → 项目心理降级,讨论
2. **扩展开发阻塞 ≥ 5 天** → 重新评估技术可行性
3. **HN 发完 48 小时 < 50 stars** → Week 3 重点改为"改定位重发"
4. **出现严重 bug 且 AI 无法修复** → 找外援 or 放弃该 feature
5. **Owner 个人情况变化**(工作 / 健康 / 家庭)→ 延期或终止

---

## 这份文件的权威性

本计划由 Owner 在 2026-04-17 正式承诺执行。

AI 在任何新会话开始时必读此文件,并在开场确认"今天是 Day ___ · 计划中今天应该做 ___"。

如果 Owner 某天说"Aether 先放一放"· AI 不要立刻同意 · 应先引用本计划询问"是今天偷懒还是正式降级?如正式降级,请更新此文件的停止条件。"

---

**计划即契约 · 契约即行动 · 行动出真章**。