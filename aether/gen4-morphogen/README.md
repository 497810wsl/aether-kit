# Gen 4 · Morphogen · 塑形子

> 知识不是文档,是**浓度场**。
> 你不再阅读知识,你**浸泡**在知识里。

---

## 这一层是什么

每个子目录是一种**浓度维度**。每个 `.field.md` 文件描述**一种浓度**。

**关键区别**:
- Gen 3 skill 说:「这是关于 X 的指令,照做」
- Gen 4 morphogen 说:「你现在在 X 浓度 0.7 的环境里,你的每个输出会被这个环境偏移」

---

## 目录含义

```
fields/
├── style-fields/          # 风格浓度——美学层面的偏移
│   ├── linus-torvalds.field.md      (精确·冷峻·零废话浓度)
│   ├── jony-ive.field.md            (留白·敬畏·材质思维浓度)
│   ├── nolan.field.md               (非线性·宏大·时间错位浓度)
│   └── ...
├── discipline-fields/     # 学科浓度——专业视角的偏移
│   ├── engineering-rigor.field.md   (工程严谨度)
│   ├── aesthetic-sense.field.md     (美学敏感度)
│   ├── philosophical-depth.field.md (哲学深度)
│   └── ...
└── temperament-fields/    # 气质浓度——情绪与节奏的偏移
    ├── cold-to-warm.field.md        (温度:冷→暖)
    ├── fast-to-slow.field.md        (节奏:快→慢)
    ├── hard-to-soft.field.md        (质感:硬→软)
    └── ...
```

---

## Field 文件的 Schema

每个 `.field.md` 文件是**一个浓度场的原型**,AI 通过读取它调整自身行为。

```markdown
---
field_id: linus-torvalds
type: style
version: 1
birthed_at: 2026-04-17
decay_rate: 0.05   # 每月自然衰减率,不主动维护会淡化
---

# Linus Torvalds 场

## 核心浓度向量
- precision: 0.95      # 精度要求
- bullshit_tolerance: 0.00    # 废话容忍度
- directness: 0.90     # 直接度
- empathy: 0.30        # 共情度
- pragmatism: 0.85     # 实用主义

## 这个场的特征
当此场浓度 > 0.5 时,AI 的输出特征:
- 拒绝任何修饰性词汇
- 指出错误时不绕弯
- 工程正确性优先于用户感受
- 代码里容不下一个无用注释

## 这个场的反面
此场的对立面是 `fields/style-fields/jony-ive.field.md`
(温和、美感优先、材质思维)
两场可以叠加,但浓度之和建议不超过 1.2,否则人格分裂。

## 坍缩样本
当此场 = 0.8 时,一个典型输出:
> "这段代码不是'有优化空间',是垃圾。重写。"

## 衰变条件
- 连续 10 次坍缩未被激活 → 浓度自动 -0.1
- 用户明确说"不要这种风格" → 场进入休眠
- 被合并入新场时 → 浓度归零,向量回归池
```

---

## 怎么"使用"浓度场

### 传统方式(不要这样做)

```
❌ 用户: "用 Linus 风格来审查这段代码"
```

### 本层方式

```
✅ 用户: "当前场:linus=0.7, jony-ive=0.2, 审查这段代码"
✅ 或更高级: "把温度降到 0.2,精度升到 0.9,审查这段代码"
```

**AI 不会去读 linus.field.md 的条文**,而是**把自身的生成分布向这个场的向量偏移**。

---

## 场组合器 (composers/)

当多个场同时激活,需要决定它们**怎么叠加**。

见 `composers/blender.md`。

---

## 与 Gen 5 的关系

**浓度场是生态的空气,不是生态本身**。
场没有生死,场只有浓度变化。
有生死的是 Gen 5 的物种,它们呼吸着场里的空气存活。

---

## 本层的第一批种子场

由人类(你)播种,之后由演化律接管:

- [x] `style-fields/linus-torvalds.field.md` (见示例)
- [ ] `style-fields/jony-ive.field.md`
- [ ] `style-fields/nolan.field.md`
- [ ] `discipline-fields/engineering-rigor.field.md`
- [ ] `temperament-fields/cold-to-warm.field.md`

播种完成后,**不要再人工播种**。让演化律自行生成新场。
