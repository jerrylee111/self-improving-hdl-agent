# Evolution Short-Stress4 主干压力实验

日期：2026-06-07

## 背景

`short-stress6` 三轮实验表明：

- `Prob104 muxdff` 是长尾任务，容易 timeout；
- `Prob063 shiftcount` 在 seed/active 下都不稳定；
- active 在前两轮 clean run 中优于 seed-only，但尚未稳定优于 no-skill；
- 第三轮 active 因 6/6 API 连接失败，不能作为 skill/cache 负例。

因此本轮构造 `short-stress4`，暂时移除 `muxdff` 与 `shiftcount`，只保留 register/FSM 主干任务，用来观察 active skill 是否能稳定修复 seed-only 的退化。

## 配置

配置文件：

```text
experiments/configs/verilogeval_evolution_short_stress4.yaml
```

任务：

| task | family |
| --- | --- |
| Prob031 dff | sequential_register |
| Prob034 dff8 | sequential_register |
| Prob111 fsm2s | sequential_fsm |
| Prob096 fsmseq | sequential_fsm |

运行命令：

```bash
uv run python experiments/run_taskset_ablation.py \
  experiments/configs/verilogeval_evolution_short_stress4.yaml \
  --no-dry-run
```

输出目录：

```text
results/taskset_ablation/verilogeval_evolution_short_stress4_20260607_194935/
```

## 汇总结果

| condition | solved | pass@k | ACPS-Iter | AST-Iter | L1 hit | candidates | API failures | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no-skill | 4/4 | 1.0 | 1.25 | 0.8 | 0/4 | 2 | 0 | 0 |
| seed-only | 2/4 | 0.5 | 3.0 | 0.3333 | 1/4 | 4 | 0 | 0 |
| active | 4/4 | 1.0 | 2.0 | 0.5 | 1/4 | 8 | 0 | 0 |

## 逐任务结果

| task | no-skill | seed-only | active |
| --- | --- | --- | --- |
| Prob031 dff | pass, 1 iter, miss | pass, 1 iter, miss | pass, 2 iter, miss |
| Prob034 dff8 | pass, 2 iter, miss | fail, 2 iter, miss | pass, 2 iter, miss |
| Prob111 fsm2s | pass, 1 iter, miss | pass, 1 iter, miss | pass, 2 iter, miss |
| Prob096 fsmseq | pass, 1 iter, miss | fail, 2 iter, hit | pass, 2 iter, hit |

## 观察

### 1. Active 修复了 seed-only 的退化

seed-only 在 `dff8` 和 `fsmseq` 上失败，active 在同样任务上全部通过：

```text
seed-only: 2/4
active:    4/4
```

这说明 active skill store 在 register/FSM 主干任务上有纠偏价值，不是简单地增加上下文噪声。

### 2. Active 尚未优于 no-skill

no-skill 本轮也是 4/4，并且 ACPS-Iter 更低：

```text
no-skill ACPS-Iter = 1.25
active   ACPS-Iter = 2.0
```

因此当前不能声称 active 比 no-skill 更强。更准确的说法是：

```text
active 能显著修复 seed-only 的负效用，但还没有证明在所有主干任务上超过无 skill 基线。
```

这也提醒我们，论文里的指标不能只用 pass@k，还必须同时报告 ACPS-Iter。

### 3. L1 hit 的正负效用需要分开记录

`fsmseq` 在 seed-only 和 active 下都是 L1 hit：

- seed-only：hit 后 fail；
- active：hit 后 pass。

这说明 `hit` 只表示缓存命中，并不表示命中内容有效。后续必须记录 hit 后的 utility：

- hit 后是否通过；
- hit 后迭代数是否下降；
- hit 后是否减少 candidate 生成；
- hit 后是否减少 evaluator 发现的错误类型；
- hit 后是否出现稳定任务族收益。

### 4. Register 类任务的检索覆盖不足

`dff` 与 `dff8` 在 seed-only/active 下主要仍是 miss，实际只加载了 pinned 的 `interface_exact`。这说明 register 类 active/candidate skill 虽然数量很多，但没有通过检索索引稳定进入 L1。

后续需要检查：

- register skill 的 tags/patterns 是否覆盖 `dff`、`dff8`；
- 检索器是否过度依赖显式 topic；
- `sequential_register` 任务族是否应有专门的 locality key。

## 对用户想法的记录

本轮继续验证了你的核心判断：

1. skill 应该在任务过程中不断生成和提取；
2. coder/evaluator 不应该看到完整外部 skill store，只能看到 L1；
3. L1 的 hit/miss 不能只按“有没有取到”判断，还要按“取到后是否产生收益”判断；
4. evaluator skill 的目标不是证明代码对，而是尽可能证明代码错；
5. 因此 evaluator skill 应该朝反例生成、断言生成、参考模型构造、覆盖点补全演进。

## 下一步

1. 重复 `short-stress4` 至少 3 轮，形成均值和方差。
2. 增加 `invalid_condition_observation` 规则，自动过滤 API failure 占比过高的 condition。
3. 为每个 L1 hit 记录 per-skill utility event。
4. 对 register 类 skill 增加更明确的 `sequential_register` locality key。
5. 对 `targeted-shiftcount` 单独实验，定位 counter skill 的负效用。

## 追加：三轮重复实验

为避免单轮偶然性，继续在 2026-06-15 运行同一 `short-stress4` 配置两次。新增输出目录：

```text
results/taskset_ablation/verilogeval_evolution_short_stress4_20260615_153257/
results/taskset_ablation/verilogeval_evolution_short_stress4_20260615_154251/
```

三轮汇总：

| condition | solved runs | pass@k runs | mean pass@k | pass@k std | ACPS runs | mean ACPS | ACPS std | timeouts |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| no-skill | 4/4, 3/4, 3/4 | 1.0, 0.75, 0.75 | 0.8333 | 0.1443 | 1.25, 2.3333, 2.3333 | 1.9722 | 0.6254 | 0, 0, 0 |
| seed-only | 2/4, 3/4, 4/4 | 0.5, 0.75, 1.0 | 0.75 | 0.25 | 3.0, 2.3333, 2.0 | 2.4444 | 0.5092 | 0, 0, 0 |
| active | 4/4, 4/4, 2/4 | 1.0, 1.0, 0.5 | 0.8333 | 0.2887 | 2.0, 1.75, 3.0 | 2.25 | 0.6614 | 0, 0, 1 |

第二轮结果：

| condition | solved | pass@k | ACPS-Iter | L1 hit | candidates | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| no-skill | 3/4 | 0.75 | 2.3333 | 0/4 | 6 | 0 |
| seed-only | 3/4 | 0.75 | 2.3333 | 1/4 | 6 | 0 |
| active | 4/4 | 1.0 | 1.75 | 1/4 | 6 | 0 |

第三轮结果：

| condition | solved | pass@k | ACPS-Iter | L1 hit | candidates | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| no-skill | 3/4 | 0.75 | 2.3333 | 0/4 | 6 | 0 |
| seed-only | 4/4 | 1.0 | 2.0 | 1/4 | 8 | 0 |
| active | 2/4 | 0.5 | 3.0 | 1/4 | 6 | 1 |

## 三轮后的结论修正

第一轮给出的“active 修复 seed-only 退化”在第二轮继续成立，但第三轮出现反转：

- 第二轮：active `4/4`，优于 no-skill/seed-only 的 `3/4`；
- 第三轮：active `2/4`，低于 seed-only 的 `4/4`；
- 第三轮 active 在 `fsmseq` 上 L1 hit 后 timeout，说明命中内容可能造成长尾或无法帮助模型摆脱错误路径。

因此当前结论应修正为：

```text
active skill 有局部收益，但还不是稳定收益；L1 cache 当前缺少命中后 utility 反馈、负效用降权和任务族级驱逐机制。
```

这比单纯证明 active 总是更好更有价值，因为它直接暴露了缓存机制必须解决的问题：cache 不能只按相似度和时间局部性加载，还必须根据历史收益更新权重。

## Hit Utility 样本

`fsmseq` 是当前最重要的 hit utility 观察点：

| run | condition | L1 event | result | iterations | note |
| --- | --- | --- | --- | ---: | --- |
| 1 | seed-only | hit | fail | 2 | hit 后未通过 |
| 1 | active | hit | pass | 2 | hit 后通过但不省迭代 |
| 2 | seed-only | hit | pass | 1 | hit 后正收益 |
| 2 | active | hit | pass | 1 | hit 后正收益 |
| 3 | seed-only | hit | pass | 2 | hit 后通过但耗时高 |
| 3 | active | hit | timeout | 0 | hit 后负收益/长尾 |

这个表说明：

1. `L1 hit` 不是有效性的充分条件；
2. 同一个任务族同一个 hit 也会产生不同结果；
3. 后续必须把每个 skill 的 utility 记录成事件流，而不是只记录 cache event；
4. eviction 不能只按 LRU，还要引入 `utility_ema`、timeout penalty、regression count。

## 下一步实验优先级更新

1. 实现 per-skill utility event：记录每个 loaded skill 对 pass、ACPS、timeout、candidate 数量的贡献。
2. 实现负效用降权：hit 后失败或 timeout 的 skill 降低 `utility_ema`。
3. 跑 `targeted-fsmseq`：只跑 `Prob096 fsmseq`，比较 no-skill/seed-only/active 多轮表现。
4. 跑 `targeted-dff8`：定位 register 类 miss 与 active 第三轮失败原因。
5. 再跑 `short-stress4`，检验加入 utility-aware eviction 后是否降低 active 方差。
