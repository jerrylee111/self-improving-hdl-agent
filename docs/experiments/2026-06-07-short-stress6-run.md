# Evolution Short-Stress6 快速压力回归实验

日期：2026-06-07

## 背景

上一轮 `evolution stress8` 暴露出两个问题：

1. seed-only 在 stress set 上明显退化；
2. LFSR 类任务存在 200 秒级长尾，会拖慢每轮实验。

因此，本轮构造 `short-stress6`，从 stress8 中移除两个 LFSR/shift 长尾任务：

- `Prob082 lfsr32`
- `Prob086 lfsr5`

保留 register/FSM/counter 的核心压力任务，用于更快观察 cache/skill 的局部效用。

## 配置

配置文件：

```text
experiments/configs/verilogeval_evolution_short_stress6.yaml
```

运行命令：

```bash
uv run python experiments/run_taskset_ablation.py \
  experiments/configs/verilogeval_evolution_short_stress6.yaml \
  --no-dry-run
```

输出目录：

```text
results/taskset_ablation/verilogeval_evolution_short_stress6_20260607_155355/
```

## 汇总结果

| condition | solved | pass@k | ACPS-Iter | AST-Iter | L1 hit | candidates | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no-skill | 5/6 | 0.8333 | 1.6 | 0.625 | 0/6 | 6 | 1 |
| seed-only | 4/6 | 0.6667 | 2.75 | 0.3636 | 2/6 | 10 | 0 |
| active | 6/6 | 1.0 | 1.5 | 0.6667 | 2/6 | 6 | 0 |

## 逐任务结果

| task | no-skill | seed-only | active |
| --- | --- | --- | --- |
| Prob104 muxdff | timeout, 0 iter, 180s | fail, 2 iter, 89s | pass, 2 iter, 169s |
| Prob031 dff | pass, 1 iter, 45s | pass, 1 iter, 38s | pass, 1 iter, 32s |
| Prob034 dff8 | pass, 2 iter, 115s | pass, 2 iter, 77s | pass, 2 iter, 103s |
| Prob111 fsm2s | pass, 1 iter, 7s | pass, 2 iter, 28s | pass, 1 iter, 12s |
| Prob096 fsmseq | pass, 2 iter, 77s | pass, 2 iter, 108s | pass, 1 iter, 82s |
| Prob063 shiftcount | pass, 2 iter, 167s | fail, 2 iter, 86s | pass, 2 iter, 85s |

## 观察

### 1. Active 在 short-stress6 上是最优条件

和 stress8 的负向结果不同，本轮 active 表现最好：

- pass@k：1.0；
- ACPS-Iter：1.5；
- 无 timeout；
- candidates 生成数量也低于 seed-only。

这说明 active skill store 并非单纯污染上下文；它在去掉 LFSR 长尾后，对 register/FSM/counter 压力集有局部正贡献。

### 2. Seed-only 仍然有稳定负例

seed-only 在 `Prob063 shiftcount` 上再次失败。上一轮 stress8 中 seed-only 也在该任务失败。

这说明 counter/shiftcount 场景下，当前 seed skill 或检索组合可能存在稳定负效用。需要后续做更细粒度定位：

- 哪个 seed skill 被加载；
- 该 skill 是否与 counter 任务真正匹配；
- 是否应引入 negative utility 记录和降权。

### 3. Active 修复了三个关键点

本轮 active 相对 seed-only 有三个明显改善：

- `Prob104 muxdff`：seed-only fail，active pass；
- `Prob096 fsmseq`：seed-only 2 iter，active 1 iter；
- `Prob063 shiftcount`：seed-only fail，active pass。

但也要注意：`muxdff` active 虽然通过，仍耗时 169 秒，说明它是长尾 register/mux 任务，不适合作为快速回归里的普通任务。

### 4. L1 hit 仍需要 utility 解释

seed-only 与 active 都是 2/6 hit，但结果差别很大：

- seed-only：4/6，ACPS 2.75；
- active：6/6，ACPS 1.5。

这进一步说明：

```text
hit rate 只能说明取到了 skill，不能说明取对了 skill。
```

下一步必须记录 hit 后 utility：

- 是否解决任务；
- 是否减少迭代；
- 是否降低 wall time；
- 是否减少 candidate 生成；
- 是否避免 timeout。

## 与 stress8 的关系

stress8 结果：

- no-skill：7/8；
- seed-only：3/8；
- active：6/8。

short-stress6 结果：

- no-skill：5/6；
- seed-only：4/6；
- active：6/6。

两个结果并不矛盾：

- stress8 包含 LFSR 长尾，暴露了 skill/cache 在长尾任务上的不稳定；
- short-stress6 去掉 LFSR 后，更清楚地看到 active 对 register/FSM/counter 有局部收益。

因此后续实验应按任务族分桶，而不是把所有 sequential 任务混在一个表里。

## 下一步

1. 对 short-stress6 重复运行至少 3 次，报告均值和方差。
2. 对 `Prob063 shiftcount` 做 seed/active 单任务重复，定位 counter seed 的负效用。
3. 对 `Prob104 muxdff` 单独做 long-tail register/mux 修复实验。
4. 实现 per-skill utility 记录，使 L1 cache 能根据实际收益做驱逐和降权。

## 追加：第二轮重复实验

为了验证第一轮 active 最优是否稳定，继续运行同一配置第二次。

输出目录：

```text
results/taskset_ablation/verilogeval_evolution_short_stress6_20260607_164823/
```

第二轮汇总：

| condition | solved | pass@k | ACPS-Iter | L1 hit | candidates | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| no-skill | 5/6 | 0.8333 | 1.8 | 0/6 | 8 | 1 |
| seed-only | 2/6 | 0.3333 | 5.0 | 2/6 | 10 | 1 |
| active | 4/6 | 0.6667 | 2.0 | 2/6 | 6 | 1 |

第二轮观察：

- no-skill 仍为 5/6，`Prob104 muxdff` 再次 timeout；
- seed-only 明显退化，只通过 2/6；
- active 仍优于 seed-only，但没有超过 no-skill；
- active 在 `Prob096 fsmseq` 上再次 1 次迭代通过，说明 FSM 场景有较稳定正向信号；
- active 在 `Prob063 shiftcount` 上本轮失败，说明 counter 场景的 active 修复不稳定；
- `Prob104 muxdff` 在 active 下也 timeout，说明上一轮 active 通过该任务不是稳定结论。

## 两轮均值

| condition | solved runs | mean pass@k | pass@k std | mean ACPS-Iter | timeout runs |
| --- | --- | ---: | ---: | ---: | --- |
| no-skill | 5/6, 5/6 | 0.8333 | 0.0 | 1.7 | 1, 1 |
| seed-only | 4/6, 2/6 | 0.5 | 0.2357 | 3.875 | 0, 1 |
| active | 6/6, 4/6 | 0.8334 | 0.2357 | 1.75 | 0, 1 |

两轮后的谨慎结论：

1. active 稳定优于 seed-only；
2. active 尚未稳定优于 no-skill；
3. seed-only 的负效用比较明显，尤其在 `shiftcount` 和部分 register/FSM 任务上；
4. `muxdff` 是长尾任务，不应继续放在快速重复实验中；
5. `fsmseq` 是 active 的相对稳定正向案例；
6. 当前结论仍需要第三轮，才能形成最小可报告均值。

## 追加：第三轮重复实验

继续运行同一配置第三次。

输出目录：

```text
results/taskset_ablation/verilogeval_evolution_short_stress6_20260607_173204/
```

第三轮原始汇总：

| condition | solved | pass@k | ACPS-Iter | L1 hit | candidates | timeouts | API failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no-skill | 4/6 | 0.6667 | 2.25 | 0/6 | 8 | 1 | 1 |
| seed-only | 4/6 | 0.6667 | 2.0 | 2/6 | 6 | 1 | 1 |
| active | 0/6 | 0.0 | N/A | 2/6 | 0 | 0 | 6 |

第三轮逐任务要点：

| task | no-skill | seed-only | active |
| --- | --- | --- | --- |
| Prob104 muxdff | timeout, 0 iter, 180s | timeout, 0 iter, 180s | APIConnectionError |
| Prob031 dff | pass, 2 iter, 36s | pass, 2 iter, 58s | APIConnectionError |
| Prob034 dff8 | pass, 2 iter, 45s | pass, 2 iter, 45s | APIConnectionError |
| Prob111 fsm2s | APIConnectionError | pass, 1 iter, 10s | APIConnectionError |
| Prob096 fsmseq | pass, 2 iter, 135s | pass, 1 iter, L1 hit, 82s | APIConnectionError |
| Prob063 shiftcount | pass, 2 iter, 102s | APITimeoutError, L1 hit | APIConnectionError |

第三轮观察：

1. active 条件的 0/6 全部来自 `APIConnectionError`，不是 evaluator 发现了 HDL 语义错误，也不是 cache 命中后证明 skill 有害。
2. 按照当前实验约定，API 连接类失败不作为 agent/cache 机制本身的有效负例，因此第三轮 active 只能记为“无效观测”，不能纳入 active skill 效用均值。
3. no-skill 与 seed-only 仍保留部分有效信息：二者都在 `muxdff` 上 timeout；seed-only 在 `fsmseq` 上 L1 hit 且 1 次迭代通过；seed-only 在 `shiftcount` 上 L1 hit 但最终 API timeout。
4. 这一轮再次说明：L1 hit 不是充分指标。`fsmseq` 的 hit 对迭代数有正向迹象，而 `shiftcount` 的 hit 没能稳定转化为通过。

## 三轮原始结果与有效观测口径

原始三轮结果：

| condition | solved runs | mean pass@k(raw) | mean ACPS-Iter(raw, solved-defined) | timeout runs | API failure runs |
| --- | --- | ---: | ---: | --- | --- |
| no-skill | 5/6, 5/6, 4/6 | 0.7778 | 1.8833 | 1, 1, 1 | 0, 0, 1 |
| seed-only | 4/6, 2/6, 4/6 | 0.5556 | 3.25 | 0, 1, 1 | 0, 0, 1 |
| active | 6/6, 4/6, 0/6 | 0.5556 | 1.75 | 0, 1, 0 | 0, 0, 6 |

有效观测口径：

- active 第三轮由于 6/6 API 失败，标记为 invalid，不用于 skill/cache 效用判断；
- no-skill 与 seed-only 第三轮只有 1/6 API 失败，仍可作为弱参考，但后续论文统计应同时报告 raw 与 non-API-filtered 两种口径；
- 当前最稳妥的结论仍以 first two clean runs 为主。

有效观测下的当前结论：

1. active 在前两轮 clean run 中稳定优于 seed-only：`6/6, 4/6` 对比 `4/6, 2/6`，平均 pass@k 为 `0.8334` 对 `0.5`。
2. active 的平均 ACPS-Iter 低于 seed-only：`1.75` 对 `3.875`，说明不仅更容易通过，而且通过成本更低。
3. active 尚未稳定优于 no-skill：前两轮 pass@k 均值都约为 `0.8333/0.8334`，差距主要体现在 active 的迭代成本略高/略低波动和具体任务族收益。
4. seed-only 的负效用已经比较清楚：它在 `shiftcount` 上连续出现失败/不稳定，即使 L1 hit 也不保证收益。
5. `muxdff` 是快速压力集里的长尾污染源；它适合做单任务 long-tail probe，不适合继续放在短回归里反复拖慢实验。
6. `fsmseq` 是目前 active/seed 检索都较有解释力的样本，可作为后续“hit 后 utility 归因”的正例。

## 对实验设计的修正

后续应增加一个运行级有效性判定：

```text
若某 condition 的 API failures / tasks >= 0.5，则该 condition 标记为 invalid_condition_observation。
```

这样可以避免把模型服务连接问题误计为 skill/cache 的负效用。与此同时，任务级记录仍保留原始失败，因为 evaluator/coder 的真实运行成本必须被记录下来。

下一轮建议拆成两个实验：

1. `short-stress4`：移除 `muxdff` 和 `shiftcount`，只验证 register/FSM 的稳定收益。
2. `targeted-shiftcount`：单独重复 `shiftcount`，观察 counter skill 为什么 L1 hit 后仍不能稳定转化为通过。

## Candidate Block 验证补充

第三轮实验后刷新 candidate 汇总与 block 合并：

- candidate 总数：272；
- unique fingerprint：28；
- duplicate groups：20；
- block 写出数量：28。

随后运行 candidate block 批量验证：

```bash
uv run python scripts/validate_candidate_blocks.py
```

输出目录：

```text
results/candidate_validation/block_validation_20260607_194311/
```

验证结果：

| decision | count |
| --- | ---: |
| keep_candidate | 13 |
| reject | 1 |
| promote | 0 |

关键结论：

1. 高频 candidate 不等于可以直接进入 active。`repair_pattern_sequential_register` 已累计 43 条，`repair_pattern_sequential_fsm` 累计 26 条，`repair_pattern_sequential_counter` 累计 23 条，但本轮验证没有产生新的 promote。
2. 当前验证门槛是保守的：只有 validation split 上 solved count 增加，或 solved count 持平但 ACPS-Iter 严格降低，才允许 promote。
3. 唯一 reject 是一个 round-robin grant block：baseline solved 与 candidate solved 都是 1，但 candidate ACPS 从 1.0 退化到 2.0。
4. 这支持当前路线：skill 应该在任务过程中持续生成，但必须经过外部验证门控再进入 active；否则 skill cache 会把“高频但未证实有效”的内容提进 L1，污染 coder/evaluator 上下文。
5. evaluator block 目前仍没有真正进入 adversarial test generation 的闭环，因此 evaluator skill 的 promote 机制需要单独实现。这个问题和你提出的“evaluator 的目标应该是证明代码错误”完全一致：evaluator skill 不能只记录检查清单，还要能生成更强的反例、断言、参考模型或覆盖点。
