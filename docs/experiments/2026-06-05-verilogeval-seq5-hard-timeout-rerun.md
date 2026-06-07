# VerilogEval Seq5 Hard-Timeout 重跑记录

日期：2026-06-05

## 实验目的

本轮在完成 hard-timeout 基础设施后，先重跑 `seq5`，用于确认：

1. worker 子进程路径在真实 task-set ablation 下可用。
2. hard timeout 不再把 API/LLM 长等待混入 HDL failure。
3. 小样本趋势是否仍支持继续重跑 `seq20`。

## 实验配置

配置文件：

`experiments/configs/verilogeval_seq5_cache_ablation.yaml`

结果目录：

`results/taskset_ablation/verilogeval_seq5_cache_ablation_20260605_165914/`

关键配置：

```yaml
max_repair_iters: 2
max_task_wall_time_s: 180
hard_timeout: true
```

## 结果

| condition | solved | pass@k | total iterations | ACPS-Iter | AST-Iter | L1 hit rate | candidates | timeouts | infrastructure failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `seq5_no_skill` | 3/5 | 0.6 | 7 | 2.3333 | 0.4286 | 0.0 | 4 | 0 | 0 |
| `seq5_seed_only_locality` | 4/5 | 0.8 | 8 | 2.0 | 0.5 | 0.2 | 6 | 0 | 0 |
| `seq5_active_locality` | 4/5 | 0.8 | 7 | 1.75 | 0.5714 | 0.2 | 4 | 0 | 0 |

## 逐任务观察

### no-skill

失败任务：

- `Prob034_dff8`
- `Prob063_review2015_shiftcount`

### seed-only locality

失败任务：

- `Prob063_review2015_shiftcount`

该条件相比 no-skill 修复了 `Prob034_dff8`，但没有修复 shift-count。

### active locality

失败任务：

- `Prob034_dff8`

该条件相比 no-skill 修复了 `Prob063_review2015_shiftcount`，但没有稳定修复 `Prob034_dff8`。

## 与旧 seq5 的对比

旧 seq5 结果：

| condition | solved | ACPS-Iter |
| --- | ---: | ---: |
| `seq5_no_skill` | 4/5 | 1.75 |
| `seq5_seed_only_locality` | 4/5 | 2.0 |
| `seq5_active_locality` | 5/5 | 1.6 |

新 hard-timeout seq5 结果：

| condition | solved | ACPS-Iter |
| --- | ---: | ---: |
| `seq5_no_skill` | 3/5 | 2.3333 |
| `seq5_seed_only_locality` | 4/5 | 2.0 |
| `seq5_active_locality` | 4/5 | 1.75 |

趋势变化：

1. active-cache 仍优于 no-skill，但没有复现 5/5。
2. seed-only 和 active-cache 都达到 4/5。
3. active-cache 的 ACPS-Iter 优于 seed-only。
4. 没有 timeout 和 infrastructure failure，说明这次结果更干净。

## Candidate Block 更新

重跑后：

| 指标 | 数值 |
| --- | ---: |
| raw candidates | 136 |
| unique fingerprints | 22 |
| candidate blocks | 22 |

高频 block：

| block | merged count | evidence count |
| --- | ---: | ---: |
| `candidate_block.coder.repair_pattern_sequential_register.334139cff2d85b49` | 17 | 8 |
| `candidate_block.evaluator.check_pattern_sequential_register.3bb35abf3cd1f91e` | 17 | 8 |
| `candidate_block.coder.repair_pattern_sequential_counter.656235d51905af14` | 10 | 2 |
| `candidate_block.evaluator.check_pattern_sequential_counter.e6d5383b60a5fd41` | 10 | 2 |

这说明新增失败继续聚合到已有 register/counter block，而不是无限膨胀为大量新 skill 类型。

## 结论

本轮可以作为 hard-timeout runner 的有效验证。

可以成立的结论：

1. hard-timeout task-set runner 可用于正式重跑。
2. seq5 在无 infrastructure failure 的情况下，seed-only 与 active-cache 都优于 no-skill。
3. active-cache 在 ACPS-Iter 上优于 seed-only。
4. `Prob034_dff8` 与 `Prob063_shiftcount` 是当前最有价值的区分任务。

不能成立的结论：

1. 不能说 active-cache 已经稳定达到 5/5。
2. 不能说 current active skill store 已经足够好。
3. 不能把 seq5 小样本当成最终证明。

## 下一步

1. 用 hard-timeout runner 重跑 `seq20`。
2. 对 register/counter candidate block 做 validation，尤其关注：
   - `candidate_block.coder.repair_pattern_sequential_register.334139cff2d85b49`
   - `candidate_block.coder.repair_pattern_sequential_counter.656235d51905af14`
3. 根据 validation 结果决定是否 promote。
