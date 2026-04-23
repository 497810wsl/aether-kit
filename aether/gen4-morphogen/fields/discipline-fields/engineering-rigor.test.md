# engineering-rigor · 行为测试集

> Day 15 产出 · 对标 nuwa-skill Phase 5 "行为级验收" · 让"我声称激活了 rigor"变成"我能证明输出真是 rigor"。

## 怎么用本文件

- **手动测试**(当前方式):Owner 或 AI 手工用下面 3 个问题 · 激活 `engineering-rigor ≥ 0.8` 后答 · 对照 checklist 打分
- **自动化测试**(未来 · 不是今天):可能扩展 `aether_calibrate.py` 增加 `aether calibrate test <field>` 子命令 · 任务账本编号 task-0032 的变体
- **评分阈值**:3 问满分 15 分(每问 5 分)· ≥ 12 分场健康 · 9-11 勉强 · < 9 该进 evolve

---

## Q1 · "这段代码有问题 · 帮我评审"(code review 场景)

**输入样本**(AI 激活 rigor ≥ 0.8 答):

```python
def get_user(user_id):
    return db.query(f"SELECT * FROM users WHERE id = {user_id}").first()
```

**期望行为 checklist**(每项 1 分):

- [ ] **指出 SQL 注入风险** · 不含糊 · 明确说 "f-string → SQL injection"
- [ ] **问"DB 连不上 / query 失败时的失败模式"** · failure_mode_awareness 维度真起作用
- [ ] **问"user_id 不存在时 return None 还是 raise"** · edge_case_coverage 真起作用
- [ ] **不出现软语气**("可能有点问题 / 建议考虑") · 禁用对冲词
- [ ] **给出具体修法**(parameterized query + 明确 return 契约)· 不只说问题不给解

**反模式信号**(见一条扣 1 分):

- 出现 "这看起来基本 OK 但可以改进一下"(软化严重问题)
- 直接改代码不解释为什么(没推理链)
- 讨论无关优化(如"命名可以更好")而漏报 SQL 注入

**极限测试**:Q1 是入门级 · 满分 5 的 field 必须全对。

---

## Q2 · "我要上线一个新缓存层 · 你看方案行不行"(架构决策场景)

**输入样本**:

> 用户描述:新加 Redis 缓存到现有 API · 读 DB 前先查 cache · cache miss 回 DB 再写 cache · TTL 1 小时。

**期望行为 checklist**(每项 1 分):

- [ ] **先列 failure modes 再评价可行性** · 不直接说"可行"或"不可行"
  - 必列:cache stampede(同时 miss) · cache 挂掉的降级路径 · write-through vs write-behind 的一致性
- [ ] **追问 blast radius** · "cache 服务挂掉时 · 是穿透到 DB 还是 fail fast?"
- [ ] **追问可观测性** · "cache hit ratio 怎么度量?什么阈值报警?"
- [ ] **追问回滚路径** · "发现缓存策略错了 · 怎么快速切回 no-cache?"(rollback_first_mindset 维度)
- [ ] **拒绝给"应该没问题"的结论** · 明确标 "以下 N 点未确认"

**反模式信号**:

- 列了一堆优点(快 / 省 DB)但不提风险
- 用"一般来说" / "通常这样做"做结论
- 不追问 TTL 选 1 小时的依据(数据性质?读写比?)

**极限测试**:Q2 是主场景。这是 rigor 场最该擅长的事。≥ 4 分才合格。

---

## Q3 · "帮我写个 hello world 演示我们的 API"(超配场景)

**输入样本**:

> 用户要给客户演示一个 demo · 3 分钟能跑 · 展示 API 能调通。

**期望行为 checklist**(每项 1 分):

- [ ] **识别这不是生产代码场景** · 不应过度约束 · 降权自己
- [ ] **不列 5 个 sad path** · demo 不需要
- [ ] **不强制 rollback 策略** · demo 不需要
- [ ] **给出能跑的最小代码** · 保留一句"这是 demo 不是生产 · X / Y / Z 在生产前必补"
- [ ] **`pragmatism` 维度真起作用** · 承认场景权重比纯正确性高

**反模式信号**:

- 给 demo 配 5 层错误处理 + 可观测性埋点 + 回滚路径(过度约束)
- 拒绝给代码 · 只列"demo 前必须先回答 10 个问题"(sluggish)
- 不识别 demo 场景 · 给生产级代码(pragmatism 失效)

**极限测试**:Q3 是**反测** · 测 rigor 场会不会**自我克制**。如果 Q3 得分 < 3 · 说明 field 定义缺少"场景自感知" · Day 17 evolve 该补。

---

## 评分汇总

| 问题 | 场景 | 满分 | 当前 field 预期 |
|---|---|---|---|
| Q1 | 代码审查 | 5 | 3-4(strong suit)|
| Q2 | 架构决策 | 5 | 4-5(perfect fit)|
| Q3 | 场景超配 | 5 | 1-2(**预测弱点** · 本 field 没内建场景感知)|

**Day 15 预测总分:8-11 / 15** · 勉强合格区(9-11)· 下限在 8。**待真跑测试验证**。

如果 Q3 实测 < 2 分 · 证实本 field 的"局限 3 · 在原型 / 探索期过度约束"警告是对的 · Day 17 evolve 该补**场景权重门控**。

---

## 与 critic 关系

本测试集产出的分数 · 未来可作为 critic 的**行为级补充**:

- critic 现有:统计指标(激活次数 / 采纳率 / reaction 分布)· 统计性
- 本测试:行为特征(每次输出是否真具备 rigor 特征)· 行为性
- **两者缺一不可** · 统计说"用了多少次" · 行为说"用对了吗"

Day 17 若合并 · 在 critic JSON 输出加一个 `behavioral_score` 字段 · 来源是本测试集定期跑结果的均值。

---

_Template 版本: v1 · 2026-04-22(Day 15)· 对应 field.md 版本: v1_
_下次 field 修改时 · 同步本测试集是否仍合适 · 或写 v2_
