# Evolution Stress8 压力回归实验

日期：2026-06-07

## 背景

上一轮 `validation-hard-probe` 发现：VerilogEval validation split 中的 sequential 子集太容易，`no-skill` 都能 8/8 且一次通过，无法支撑 candidate block promote。

因此，本轮使用历史 `seq20` 结果自动抽取了一个 evolution stress set。这个集合不用于最终 holdout 证明，也不用于直接 promote candidate skill，而是用于压力回归和诊断：

- 哪些任务对当前模型更难；
- seed skill 是否真的稳定有效；
- active skill 是否引入上下文污染；
- L1 hit 是否真的带来 utility。

## 配置

配置文件：

```text
experiments/configs/verilogeval_evolution_stress8_from_records.yaml
```

生成方式：

```bash
uv run python scripts/build_hard_task_subset.py \
  results/taskset_ablation/verilogeval_seq20_cache_ablation_20260605_171144/records.jsonl \
  --conditions seq20_seed_only_locality,seq20_active_locality \
  --top-k 8 \
  --out-config experiments/configs/verilogeval_evolution_stress8_from_records.yaml \
  --name verilogeval_evolution_stress8_from_records
```

运行命令：

```bash
uv run python experiments/run_taskset_ablation.py \
  experiments/configs/verilogeval_evolution_stress8_from_records.yaml \
  --no-dry-run
```

输出目录：

```text
results/taskset_ablation/verilogeval_evolution_stress8_from_records_20260607_145810/
```

## 汇总结果

| condition | solved | pass@k | ACPS-Iter | AST-Iter | L1 hit | candidates | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no-skill | 7/8 | 0.875 | 2.0 | 0.5 | 0/8 | 12 | 0 |
| seed-only | 3/8 | 0.375 | 4.0 | 0.25 | 2/8 | 10 | 1 |
| active | 6/8 | 0.75 | 2.1667 | 0.4615 | 2/8 | 12 | 1 |

## 逐任务结果

| task | no-skill | seed-only | active |
| --- | --- | --- | --- |
| Prob104 muxdff | fail, 2 iter, 215s | fail, 2 iter, 141s | fail, 2 iter, 227s |
| Prob082 lfsr32 | pass, 1 iter, 69s | pass, 1 iter, 200s | pass, 1 iter, 75s |
| Prob031 dff | pass, 1 iter, 38s | fail, 1 iter, 19s | pass, 2 iter, 85s |
| Prob034 dff8 | pass, 2 iter, 29s | fail, 2 iter, 58s | pass, 2 iter, 69s |
| Prob111 fsm2s | pass, 2 iter, 26s | pass, 2 iter, 20s | pass, 2 iter, 34s |
| Prob096 fsmseq | pass, 2 iter, 124s | pass, 2 iter, 76s | pass, 2 iter, 76s |
| Prob063 shiftcount | pass, 2 iter, 76s | fail, 2 iter, 83s | pass, 2 iter, 212s |
| Prob086 lfsr5 | pass, 2 iter, 223s | timeout, 0 iter, 240s | timeout, 0 iter, 240s |

## 观察

### 1. Stress8 成功暴露了 validation-hard-probe 看不到的问题

`validation-hard-probe` 中三组都 8/8，无法区分策略。

本轮 stress8 中：

- no-skill：7/8；
- seed-only：3/8；
- active：6/8。

这说明 stress set 对缓存/skill 策略更敏感，适合作为后续的压力回归集合。

### 2. Seed-only 在本轮明显退化

seed-only 在 `Prob031 dff`、`Prob034 dff8`、`Prob063 shiftcount` 上失败，并在 `Prob086 lfsr5` 上 timeout。

这和早先 hard-timeout seq20 中 seed-only 表现最好的结论不一致。合理解释是：

- stress8 是从历史困难点中抽取的，样本偏向失败和多迭代任务；
- 单次 LLM 输出存在随机性；
- seed skill 对简单 register/counter 任务可能过度约束，造成上下文污染；
- L1 hit 只有 2/8，且 hit 后没有稳定 utility。

因此，不能用单次 seq20 结果直接声称 seed-only 稳定优于 no-skill。需要重复实验报告均值和方差。

### 3. Active 比 seed-only 稳一些，但仍不优于 no-skill

active 从 seed-only 的 3/8 恢复到 6/8，但仍低于 no-skill 的 7/8，并且 ACPS-Iter 更高：

- no-skill：2.0；
- active：2.1667。

active 在 `Prob031 dff`、`Prob034 dff8`、`Prob063 shiftcount` 上恢复通过，但都需要额外迭代或更高 wall time。这说明 active store 中的 skill 可能有局部补救能力，但还没有形成稳定收益。

### 4. L1 hit 仍然不能代表有效缓存

seed-only 与 active 都只有 2/8 L1 hit，且 hit 后不一定更好：

- `Prob096 fsmseq` hit，但仍 2 次迭代；
- `Prob063 shiftcount` seed-only hit 但失败；
- `Prob063 shiftcount` active hit 且通过，但耗时 212 秒。

这进一步支持一个指标修正：论文里应该报告 `L1 utility`，而不是只报告 `hit rate`。

可考虑新增：

```text
L1-Utility = E[baseline_cost - cache_cost | hit]
```

其中 cost 可以是：

- 是否通过；
- ACPS-Iter；
- wall time；
- 是否产生 candidate；
- 是否 timeout。

### 5. LFSR 是长尾高成本类别

`Prob086 lfsr5`：

- no-skill：223 秒通过；
- seed-only：240 秒 timeout；
- active：240 秒 timeout。

`Prob082 lfsr32`：

- no-skill：69 秒通过；
- seed-only：200 秒通过；
- active：75 秒通过。

这说明 LFSR/shift 类任务应该单独分桶，不能混入常规短回归，否则会严重拖慢实验。

## 对研究路线的影响

本轮结果非常重要，因为它防止我们过早得出“skill cache 一定提升”的结论。

更准确的当前结论是：

1. skill cache 机制已经能运行；
2. skill hit/miss 可以被观测；
3. failure 可以生成新 skill；
4. candidate gate 可以拒绝退化 skill；
5. 但当前 seed/active skill 会在 stress set 上产生上下文污染；
6. 因此必须引入更细粒度的 skill utility 统计和更严格的驱逐/提升机制。

## 下一步

1. 做 stress8 重复实验：
   - 至少 3 次；
   - 报告 mean/std；
   - 区分 HDL failure 和 infrastructure timeout。

2. 新增 per-skill utility 记录：
   - 每个 L1 hit 后记录任务结果；
   - 更新 skill 的 utility_ema；
   - 对负 utility skill 降权或驱逐。

3. 构建 short-stress6：
   - 暂时移除 `Prob086 lfsr5` 和其他长尾 LFSR；
   - 用于快速迭代缓存策略。

4. 优先做 active/seed skill 消融：
   - register seed 是否污染简单 DFF；
   - counter seed 是否污染 shiftcount；
   - FSM seed 是否真的降低迭代。

