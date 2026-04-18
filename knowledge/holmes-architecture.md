# Holmes 架构 — 一人全包，自动路由

> 文档日期：2026-03-20（与代码同步）
> 对应项目：<USER>/MemoryPalace

---

## 根本问题

问题有简有繁，一刀切的检索+回答浪费 token 且答案片面。
需要自动判断复杂度，走不同路径。

---

## 核心设计：全部是 Holmes 一个人

不分三角色。评估、速答、深度推理都是 Holmes 自己做，只是功能分步。
唯一的"第二人"是 Mycroft（哥哥），只在 complex 路径最后做质控审查。

```
用户问题
  │
  ▼
【评估】Holmes 看一眼，判断 simple / complex
  → 1 次 LLM，返回 JSON
  │
  ├─ simple → query() top5 → Holmes 速答（1次LLM）→ 共 2 次
  │
  └─ complex → 拆子问题 → 各自 query() → 去重 top8
               → Holmes 深度推理（1次LLM）→ Mycroft 审查（1次LLM）→ 共 3 次
```

---

## Holmes 人设

全程福尔摩斯，不引入华生。

**口癖**：
- "显然……"、"初步观察……"、"数据不会说谎……"
- 冷静克制，偶尔带傲慢的幽默
- 一句能说清的不用两句

**主人画像（USER_PROFILE，嵌入所有 prompt）**：
- 先找根本问题再建框架，系统化 + 层次感
- 对比表格做决策，最小可行方案优先
- 蒸馏思维（提炼本质），厌恶手动维护
- 问"怎么做"→ 找自动化路径；问"是什么"→ 建心智模型

这是"个人标签"——别人 clone 代码后 Holmes 会"读不懂他们"。

---

## 文件结构

```
holmes.py      — prompt 定义 + LLM 调用函数
                 USER_PROFILE（主人画像，所有 prompt 共用）
                 EVALUATE_PROMPT（评估）
                 HOLMES_QUICK_PROMPT（速答）
                 HOLMES_DEEP_PROMPT（深度推理）
                 MYCROFT_PROMPT（审查）

retriever.py   — 检索引擎 + 路由入口
                 query()          — 纯向量搜索
                 answer()         — 旧接口，简单检索+回答
                 answer_holmes()  — 新接口，自动路由推理

bot.py         — Discord Bot，命令路由 + embed 展示
```

---

## 记忆打标签

MCP `remember()` 支持 tag 参数：
```python
remember(content, source="mcp_manual", tag="偏好")
```
tag 存入 metadata，可用于分类（偏好、项目笔记、决策等）。

---

## 关键决策备忘

| 决策 | 选择 | 原因 |
|------|------|------|
| 角色 | 全程 Holmes 一人，不分角色 | 统一人格 |
| 华生 | 不引入 | 不分裂 |
| Mycroft | 仅 complex 路径质控 | 只审查，不参与推理 |
| 评估+拆题 | 1次LLM | 省token |
| 推理+结论 | 1次LLM，--- 分隔 | 简单可控 |
| 检索 | 纯向量搜索，无LLM | 快速 |
| 去重 | text前50字符判重 | 简单够用 |
| 人设标签 | USER_PROFILE 嵌入 prompt | 个人印记 |
