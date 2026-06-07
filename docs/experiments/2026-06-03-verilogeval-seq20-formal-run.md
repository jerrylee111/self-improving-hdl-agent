# VerilogEval Seq20 正式实验记录

日期：2026-06-03

## 实验目的

本轮按照前一阶段计划，运行 VerilogEval sequential-heavy task set 的正式 ablation。目标是初步检验：

1. L1 skill cache 是否能在相关任务序列中带来收益。
2. seed skill、active skill 是否优于 no-skill baseline。
3. task-set 级实验是否已经足够稳定，可以作为论文主实验。

## 实验配置

配置文件：

`experiments/configs/verilogeval_seq20_cache_ablation.yaml`

结果目录：

`results/taskset_ablation/verilogeval_seq20_cache_ablation_20260603_090903/`

任务数：20

条件：

| condition | active skills | policy |
| --- | --- | --- |
| `seq20_no_skill` | false | no_skill |
| `seq20_seed_only_locality` | false | locality_aware |
| `seq20_active_locality` | true | locality_aware |

最大修复迭代：2

单任务 wall-time budget：240s

注意：当前 timeout 仍是协作式，只能在 attempt 边界检查，不能强制中断正在等待的单次 LLM 请求。

## 原始结果

| condition | solved | pass@k | total iterations | ACPS-Iter | AST-Iter | L1 hit rate | candidates | API failures | timeouts | mean wall time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `seq20_no_skill` | 18/20 | 0.90 | 24 | 1.3333 | 0.7500 | 0.00 | 8 | 0 | 1 | 67.139s |
| `seq20_seed_only_locality` | 15/20 | 0.75 | 26 | 1.7333 | 0.5769 | 0.20 | 12 | 3 | 1 | 246.107s |
| `seq20_active_locality` | 15/20 | 0.75 | 28 | 1.8667 | 0.5357 | 0.20 | 16 | 2 | 0 | 88.880s |

原始结果显示：本轮 no-skill baseline 反而最好，seed-only 和 active-cache 都下降。

## 剔除 API Failure 后的有效结果

| condition | effective solved | effective tasks | effective pass rate | HDL failed tasks |
| --- | ---: | ---: | ---: | --- |
| `seq20_no_skill` | 18 | 20 | 0.900 | `Prob096_fsmseq`, `Prob104_muxdff` |
| `seq20_seed_only_locality` | 15 | 17 | 0.882 | `Prob104_muxdff`, `Prob034_dff8` |
| `seq20_active_locality` | 15 | 18 | 0.833 | `Prob096_fsmseq`, `Prob084_q12`, `Prob063_shiftcount` |

API failure 分布：

| condition | API failed tasks |
| --- | --- |
| `seq20_no_skill` | none |
| `seq20_seed_only_locality` | `Prob063_shiftcount`, `Prob035_count1to10`, `Prob116_m2014_q3` |
| `seq20_active_locality` | `Prob086_lfsr5`, `Prob082_lfsr32` |

即使剔除 API failure，本轮 seed-only 和 active-cache 也没有超过 no-skill。

## 关键任务观察

### 正向信号

`Prob096_review2015_fsmseq`

- no-skill：失败
- seed-only locality：通过
- active locality：失败

这说明 seed skill 对 FSM 类任务可能有帮助，但 active-cache 的结果不稳定。

`Prob104_mt2015_muxdff`

- no-skill：失败
- seed-only locality：失败
- active locality：通过

这是 active-cache 的正向案例，但该任务也有较长 wall time 和 timeout 风险，因此需要重复实验确认。

### 负向信号

`Prob034_dff8`

- no-skill：通过
- seed-only locality：失败
- active locality：通过

说明 seed skill 可能产生提示干扰，尤其当检索只拿到很泛的 `interface_exact` 或通用 sequential rule 时。

`Prob084_ece241_2013_q12`

- no-skill：通过
- seed-only locality：通过
- active locality：失败

active-cache 在该题生成了错误的 part-select，例如 `Q[0:6]`，说明当前 skill 对 shift/vector ordering 的约束不够具体。

`Prob063_review2015_shiftcount`

- no-skill：通过，但耗时长
- seed-only locality：API timeout
- active locality：HDL 失败

该题在 seq5 中 active-cache 曾通过，本轮又失败，说明任务存在明显采样波动，需要重复实验或更稳定的模型调用策略。

## Candidate Store 变化

seq20 运行后：

| 指标 | 数值 |
| --- | ---: |
| raw candidates | 120 |
| unique fingerprints | 22 |
| duplicate groups | 16 |
| candidate blocks | 22 |

高频 block：

| block type | merged count | source tasks |
| --- | ---: | --- |
| coder sequential register | 12 | `Prob031_dff`, `Prob034_dff8`, `Prob104_muxdff` |
| evaluator sequential register | 12 | `Prob031_dff`, `Prob034_dff8`, `Prob104_muxdff` |
| coder sequential counter | 7 | `Prob063_shiftcount` |
| evaluator sequential counter | 7 | `Prob063_shiftcount` |

这说明正式实验虽然没有证明 active-cache 已经优于 baseline，但确实持续生成并聚合了有价值的 failure-derived skill block。

## 结论

本轮是一次正式 task-set 实验试跑，但还不能作为最终论文主结论。

可以成立的结论：

1. task-set ablation runner 可用。
2. L1 cache hit/miss、candidate yield、API failure、timeout 都已经可记录。
3. failure-derived candidate block 会自然累积，并且高度重复，证明 block 化管理是必要的。
4. 当前 seed/active skill 质量还不足，不能稳定提升 VerilogEval seq20。

不能成立的结论：

1. 不能说 active-cache 已经显著提升 pass rate。
2. 不能说 locality-aware 当前映射策略已经有效。
3. 不能把本轮 wall time 直接当模型能力指标，因为 API timeout/connection error 严重影响 seed-only 和 active 条件。

## 下一步修正

1. 实现硬超时：每个 task run 放到 subprocess 中，超过 wall-time 直接终止，避免单次 LLM 请求拖垮整组实验。
2. 增加 API failure retry/隔离：API failure 不应与 HDL failure 混入同一个能力指标。
3. 验证并提升 block：
   - `candidate_block.coder.repair_pattern_sequential_register.334139cff2d85b49`
   - `candidate_block.coder.repair_pattern_sequential_counter.656235d51905af14`
4. 增加 shift/vector ordering seed skill，针对 `Q[0:6]` 这类 part-select 方向错误。
5. 重跑 seq20，至少重复 3 次，报告均值和方差。
