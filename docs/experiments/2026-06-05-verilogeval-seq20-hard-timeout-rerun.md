# VerilogEval Seq20 Hard-Timeout 重跑记录

日期：2026-06-05

## 实验目的

在完成 hard-timeout task runner 后，重跑 VerilogEval sequential-heavy `seq20` ablation，观察去除长时间 LLM/API 等待污染后，skill cache 条件是否比 no-skill 更可靠。

## 实验配置

配置文件：

`experiments/configs/verilogeval_seq20_cache_ablation.yaml`

结果目录：

`results/taskset_ablation/verilogeval_seq20_cache_ablation_20260605_171144/`

关键配置：

```yaml
max_repair_iters: 2
max_task_wall_time_s: 240
hard_timeout: true
```

## 结果

| condition | solved | pass@k | total iterations | ACPS-Iter | AST-Iter | L1 hit rate | candidates | timeouts | infrastructure failures | mean wall time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `seq20_no_skill` | 15/20 | 0.75 | 25 | 1.6667 | 0.6000 | 0.00 | 14 | 2 | 2 | 65.384s |
| `seq20_seed_only_locality` | 19/20 | 0.95 | 24 | 1.2632 | 0.7917 | 0.20 | 8 | 0 | 0 | 51.668s |
| `seq20_active_locality` | 18/20 | 0.90 | 27 | 1.5000 | 0.6667 | 0.20 | 14 | 0 | 0 | 53.936s |

## 与上一轮 seq20 的差异

上一轮 soft-timeout seq20：

| condition | solved | pass@k | API failures | timeouts |
| --- | ---: | ---: | ---: | ---: |
| `seq20_no_skill` | 18/20 | 0.90 | 0 | 1 |
| `seq20_seed_only_locality` | 15/20 | 0.75 | 3 | 1 |
| `seq20_active_locality` | 15/20 | 0.75 | 2 | 0 |

本轮 hard-timeout seq20：

| condition | solved | pass@k | infrastructure failures | timeouts |
| --- | ---: | ---: | ---: | ---: |
| `seq20_no_skill` | 15/20 | 0.75 | 2 | 2 |
| `seq20_seed_only_locality` | 19/20 | 0.95 | 0 | 0 |
| `seq20_active_locality` | 18/20 | 0.90 | 0 | 0 |

本轮结果更适合作为阶段性主实验，因为长时间卡住的任务被截断为 infrastructure failure，不再拖到上千秒。

## 关键任务观察

### no-skill 失败/超时

| task | type | 观察 |
| --- | --- | --- |
| `Prob086_lfsr5` | infrastructure timeout | 240s hard timeout |
| `Prob095_review2015_fsmshift` | HDL failure | `shift_ena` mismatch |
| `Prob084_ece241_2013_q12` | HDL failure | `Z` mismatch |
| `Prob104_mt2015_muxdff` | HDL failure | `Q` first-cycle mismatch |
| `Prob116_m2014_q3` | infrastructure timeout | 240s hard timeout |

### seed-only locality

唯一 HDL failure：

| task | 观察 |
| --- | --- |
| `Prob104_mt2015_muxdff` | `Q` first-cycle mismatch |

seed-only 修复/避免了 no-skill 中的多个问题：

- `Prob086_lfsr5`：no-skill timeout，seed-only pass。
- `Prob095_fsmshift`：no-skill fail，seed-only pass。
- `Prob084_q12`：no-skill fail，seed-only pass。
- `Prob116_m2014_q3`：no-skill timeout，seed-only pass。
- `Prob063_shiftcount`：seed-only L1 hit，1 iteration pass。

### active locality

失败任务：

| task | 观察 |
| --- | --- |
| `Prob082_lfsr32` | LFSR mismatch, very high mismatch count |
| `Prob031_dff` | procedural assignment to wire |

active locality 的正向点：

- `Prob104_muxdff`：no-skill 和 seed-only 都失败，active pass。
- `Prob084_q12`：active 1 iteration pass，本轮没有出现 part-select 方向错误。
- `Prob063_shiftcount`：L1 hit，2 iterations pass。

active locality 的负向点：

- `Prob082_lfsr32`：seed-only pass，active fail。
- `Prob031_dff`：seed-only pass，active fail。

这说明 active store 里已有 arbiter 类 skill 不一定适合 VerilogEval sequential tasks；active skill 数量和检索映射都还需要控制。

## Candidate Block 更新

本轮后：

| 指标 | 数值 |
| --- | ---: |
| raw candidates | 172 |
| unique fingerprints | 28 |
| candidate blocks | 28 |

高频 block：

| block | merged count | evidence count |
| --- | ---: | ---: |
| `candidate_block.coder.repair_pattern_sequential_register.334139cff2d85b49` | 23 | 8 |
| `candidate_block.evaluator.check_pattern_sequential_register.3bb35abf3cd1f91e` | 23 | 8 |
| `candidate_block.coder.repair_pattern_sequential_counter.656235d51905af14` | 12 | 2 |
| `candidate_block.evaluator.check_pattern_sequential_counter.e6d5383b60a5fd41` | 12 | 2 |
| `candidate_block.coder.repair_pattern_sequential_fsm.43e4ce22df583720` | 9 | 9 |
| `candidate_block.evaluator.check_pattern_sequential_fsm.9aa0747c6b78fce4` | 9 | 9 |

## 阶段性结论

本轮首次给出了比较清晰的正向结果：

1. hard-timeout 后，seed-only locality 在 seq20 上显著优于 no-skill。
2. active locality 也优于 no-skill，但低于 seed-only。
3. L1 hit rate 仍只有 0.2，说明 cache 映射还有提升空间。
4. active skill store 目前存在领域不匹配/干扰风险，不应盲目扩大 active。
5. candidate block 继续聚合到 register/counter/FSM，说明下一步应该验证并提升这些 block，而不是继续生成更多未验证 candidate。

## 下一步

1. 对以下 coder blocks 做 validation：
   - `candidate_block.coder.repair_pattern_sequential_register.334139cff2d85b49`
   - `candidate_block.coder.repair_pattern_sequential_counter.656235d51905af14`
   - `candidate_block.coder.repair_pattern_sequential_fsm.43e4ce22df583720`
2. 如果 block 在 validation split 上严格改善，则 promote 到 active。
3. 加入 shift/vector ordering seed skill，针对 `Prob084_q12` 类错误。
4. 重跑 seq20，增加 `validated-block-cache` 条件，与 seed-only 和 active locality 对比。
