# 阶段报告：Task-Set Ablation 与 Candidate 去重准备

日期：2026-06-03

## 当前实验位置

当前系统已经从单任务 demo 进入 task-set 级实验准备阶段。目标不再只是证明 coder/evaluator loop 能跑，而是要证明：

1. L1 skill cache 对一组相关任务有收益。
2. skill 不会因为一次失败就污染 active store。
3. 自动生成的 candidate skill 可以被统计、去重、验证和提升。

## 本阶段新增内容

### 1. Task-set ablation runner

新增：

`experiments/run_taskset_ablation.py`

该 runner 的特点是：同一个 condition 下按任务序列跑完整 task set，并让 L1 cache 在任务之间保留。这更接近我们要证明的“时间局部性”和“问题局部性”：

```text
condition
  -> task 1 lookup/fill L1
  -> task 2 may hit L1
  -> task 3 may hit L1
  -> ...
  -> measure pass@k, ACPS-Iter, L1 hit rate, candidate yield
```

### 2. VerilogEval seq20 配置

新增：

`experiments/configs/verilogeval_seq20_cache_ablation.yaml`

任务数：20

任务构成：

- LFSR：2
- FSM：3
- shift/rotate：5
- register/DFF：6
- counter：3
- 补充 misc HDL：1

实验条件：

| condition | active skills | policy |
| --- | --- | --- |
| `seq20_no_skill` | false | no_skill |
| `seq20_seed_only_locality` | false | locality_aware |
| `seq20_active_locality` | true | locality_aware |

该配置已经 dry-run 通过。

### 3. Candidate fingerprint 汇总

新增：

`scripts/summarize_candidate_skills.py`

输出：

`skills/metrics/candidate_summary.json`

当前统计：

| 指标 | 数值 |
| --- | --- |
| candidate_count | 68 |
| unique_fingerprints | 12 |
| duplicate_groups | 8 |

这说明 candidate store 里存在大量重复信息。典型重复：

| fingerprint | count | agent | name | source task |
| --- | ---: | --- | --- | --- |
| `7b1013c47cd1c831` | 17 | coder | repair_pattern_sequential_arbiter | `local_round_robin_arbiter2_enable` |
| `05bf45006c5e8343` | 17 | evaluator | check_pattern_sequential_arbiter | `local_round_robin_arbiter2_enable` |
| `f64807dce48b82c1` | 8 | coder | repair_pattern_sequential_arbiter | `local_round_robin_arbiter2` |
| `1fad9bbe036516b2` | 8 | evaluator | check_pattern_sequential_arbiter | `local_round_robin_arbiter2` |

## 实验意义

这个结果支持用户最初的 cache 类比：如果外部存储不做规范化、映射和去重，L1 cache 面对的不是“高质量 skill block”，而是一堆重复、低密度的碎片。后续 active store 应该更像缓存行/块：

- 一个 fingerprint 代表一个候选 skill block。
- 多次失败证据累积到同一个 block。
- promotion 针对 block，而不是针对每个 timestamp 文件。
- L1 装入的是合并后的 active block，而不是重复 candidate。

## 当前缺口

1. `seq20` 还没有正式跑完整实验，目前只完成 dry-run。
2. candidate 已经能 fingerprint，但还没有自动 merge。
3. evaluator skill 还没有接入 adversarial test generation，因此 evaluator candidate 仍只能 pending。
4. timeout 目前是协作式，单次 LLM 调用仍不能强制中断。

## 下一步

优先级建议：

1. 跑 `verilogeval_seq20_cache_ablation.yaml` 的正式实验，得到第一张 task-set ablation 表。
2. 实现 candidate merge，把 68 个 candidate 压缩成 12 个 candidate blocks。
3. 将 evaluator base skill 接入 adversarial stimulus generation，让 evaluator skill 可以被验证。
4. 在 holdout split 上重复 active-cache vs seed-only，对外证明 skill cache 的泛化收益。

## 追加进展：Seq5 Task-Set Ablation

为了避免第一次直接运行 20 题 × 3 条件导致耗时过长，本轮先新增并运行了一个 5 题 task-set ablation。

配置：

`experiments/configs/verilogeval_seq5_cache_ablation.yaml`

结果目录：

`results/taskset_ablation/verilogeval_seq5_cache_ablation_20260603_083222/`

任务：

| task | family |
| --- | --- |
| `Prob031_dff` | sequential_register |
| `Prob034_dff8` | sequential_register |
| `Prob035_count1to10` | sequential_counter |
| `Prob063_review2015_shiftcount` | sequential_counter |
| `Prob085_shift4` | sequential_shift |

结果：

| condition | solved | pass@k | ACPS-Iter | AST-Iter | L1 hit rate | candidates | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `seq5_no_skill` | 4/5 | 0.8 | 1.75 | 0.5714 | 0.0 | 4 | 0 |
| `seq5_seed_only_locality` | 4/5 | 0.8 | 2.0 | 0.5 | 0.2 | 6 | 0 |
| `seq5_active_locality` | 5/5 | 1.0 | 1.6 | 0.625 | 0.2 | 6 | 0 |

关键观察：

1. `Prob063_review2015_shiftcount` 是区分条件的关键任务：
   - no-skill：失败
   - seed-only locality：失败
   - active locality：通过
2. seed-only 并没有稳定优于 no-skill，说明“有 skill”不天然等于有效；skill 内容质量和检索映射很重要。
3. active locality 在这个小样本上同时提升了 pass@k 和 ACPS-Iter，但样本量只有 5，不能作为最终证明。
4. L1 hit rate 只有 0.2，说明当前映射规则对 register/shift/counter 任务的复用能力还不够强。

这轮结果可以作为论文中的 pilot experiment，而不是最终主实验。

## 追加进展：Candidate Block Merge

新增：

`scripts/merge_candidate_skills.py`

该脚本把重复 candidate 按 fingerprint 合并为 candidate block，输出到：

`skills/candidate_blocks/`

seq5 运行后统计为：

| 指标 | 数值 |
| --- | ---: |
| raw candidates | 84 |
| candidate blocks | 14 |

典型新 block：

| block | merged count | evidence count |
| --- | ---: | ---: |
| `candidate_block.coder.repair_pattern_sequential_register.334139cff2d85b49` | 5 | 4 |
| `candidate_block.evaluator.check_pattern_sequential_register.3bb35abf3cd1f91e` | 5 | 4 |
| `candidate_block.coder.repair_pattern_sequential_counter.656235d51905af14` | 4 | 2 |
| `candidate_block.evaluator.check_pattern_sequential_counter.e6d5383b60a5fd41` | 4 | 2 |

这个结果说明：skill 外部存储应当以 block 为单位管理，而不是以每次失败生成的 timestamp 文件为单位管理。后续 validation/promotion 也应针对 block 进行。

## 更新后的下一步

1. 将 `scripts/validate_candidate_skill.py` 扩展到支持 candidate block。
2. 验证 sequential_register / sequential_counter block 是否能在 validation split 上严格改善。
3. 跑完整 `verilogeval_seq20_cache_ablation.yaml`。
4. 把 evaluator block 接入 adversarial test generation，让 evaluator skill 从 pending 进入可验证状态。
