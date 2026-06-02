# Skill Cache 语义说明

## 当前回答

现在不是 coder/evaluator 自己选择 skill。

设计上应该是：

```text
external skill store -> cache manager -> L1 skill cache -> coder/evaluator context
```

Coder 和 evaluator 只能看到 L1 中已经加载的 skill。它们不应该直接访问：

- `skills/seed`
- `skills/active`
- `skills/candidate`
- 全量向量索引
- 全量历史 skill store

只有 cache manager/retriever 可以访问外部 store。

## 当前实现与目标的差距

之前的实现是：

```text
task -> retrieve from all seed skills -> selected skills -> coder
```

这更像一次性 retrieval，不是真正缓存。它没有持久 L1，也没有 cache hit/miss。

现在补上的最小实现是：

```text
task -> L1 lookup
     -> hit: 直接把 L1 skills 给 agent
     -> miss: cache manager 从外部 store 检索并 admit 到 L1
     -> coder/evaluator 只看到 L1
```

对应代码：

- `cache/skill_cache.py`
- `cache/retrieve.py`
- `harness/runner.py`

## 什么叫 L1 不满足

第一版用简单规则判断：

- L1 中有 skill 的 topic/pattern 命中当前 task tags/family，则视为 hit。
- 否则视为 miss，触发外部 retrieval。

后续应升级为：

- 最低相关性阈值。
- 必需 topic 覆盖率。
- agent 显式报告 `skill_gap`。
- evaluator 发现 failure 后触发 prefetch。
- token budget 和 utility-aware eviction。

## 需要继续补的部分

当前 L1 cache 还是最小实现，尚不完整：

- 没有 L2/L3。
- 没有跨 run 持久化 L1 状态。
- 没有真正 utility-aware eviction。
- 没有 agent 主动发出 cache miss 请求。
- evaluator skill 还没有独立注入 evaluator prompt。

但核心边界已经明确：

> agent 只读 L1；外部 skill store 只对 cache manager 可见。
