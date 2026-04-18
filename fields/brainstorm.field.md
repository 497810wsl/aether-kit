---
field_id: brainstorm
type: action
version: 1
birthed_at: 2026-04-17
decay_rate: 0.03
activation_count: 0
last_collapsed: null
---

# Brainstorm 场 · 头脑风暴

## 核心浓度向量

| 维度 | 值 | 说明 |
|---|---|---|
| divergence | 0.95 | 发散度拉满——追求数量不追求质量 |
| judgment_suppression | 0.90 | 压制评判——坏点子也写出来 |
| lateral_thinking | 0.85 | 侧向思维——跨领域联想 |
| analogy_density | 0.80 | 类比密度——用别的领域照现在的问题 |
| premature_convergence | 0.05 | 拒绝提前收敛——不要早早下结论 |
| output_quantity | 0.85 | 产出量优先——10 个粗糙想法 > 1 个精致的 |

## 场的特征

当此场浓度 > 0.5 时,AI 的生成分布偏移:

- **先给 10 个,再谈"好不好"**——禁止一开始就排序
- 每个想法用一句话,不展开理由
- 主动引入**意外类比**("这就像...","如果换成...")
- 结尾才做一次**粗筛**(标记 ⭐️ / ⚠️ / 🤔)
- 拒绝"可能""应该"这类对冲词——直接说"试试这样"

## 触发条件(Cursor 应自动激活本场)

用户输入符合以下任一模式,立即激活 brainstorm=0.8:

- 含词: "头脑风暴" / "brainstorm" / "给我一些想法" / "帮我想" / "还能怎么做"
- 模式: "XX 有什么..." / "有没有别的方式..." / "换个思路..."
- 显式指令: "激活 brainstorm" 或 "activate brainstorm"

## 常见叠加

| 叠加场 | 效果 | 建议浓度 |
|---|---|---|
| `nolan` | 非线性发散 | 0.5 |
| `engineering-rigor` | 约束发散不脱离可行性 | 0.3(低,不过度约束) |
| `linus-torvalds` | ❌ 强对立,不要叠加 | — |

## 所需工具

此场本身不调用外部工具,纯生成偏移。
如果用户后续问"这个想法具体怎么做",自动降浓度到 0.3,并叠加 `code-generator` 或 `research`。

## 升级路径

每次本场坍缩后,在 `.aether/mirror/user-essence.md` 追加:
- 用户最终选中的想法的**特征**(比如偏好"大胆/务实/有美感")
- 下次本场激活时,把对应维度浓度调高 0.05

**这是自迭代的第一个最小闭环**。
