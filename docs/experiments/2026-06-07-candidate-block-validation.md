# Candidate Block 批量验证实验

日期：2026-06-07

## 背景

在 hard-timeout 版 `seq20` 实验之后，系统已经能稳定完成：

- 任务运行；
- L1 skill cache 检索；
- coder/evaluator 迭代；
- failure-driven candidate skill 生成；
- candidate skill fingerprint 去重；
- candidate block 合并。

但上一轮实验也暴露出一个核心问题：`active-cache` 没有稳定超过 `seed-only`。这说明自动生成的 skill 不能直接进入 active store，而必须先经过 validation gate。

本轮实验的目标是验证：

1. candidate block 是否能在 validation split 上带来严格收益；
2. 哪些 block 应该 promote、保留、拒绝；
3. evaluator block 当前是否已经具备可验证条件。

## 新增工具

新增批量验证脚本：

```bash
uv run python scripts/validate_candidate_blocks.py
```

脚本能力：

- 遍历 `skills/candidate_blocks/*.yaml`；
- 按 `agent` 过滤 coder/evaluator/all；
- 逐个调用现有 `scripts/validate_candidate_skill.py`；
- 聚合每个 block 的 `decision`、baseline summary、candidate summary；
- 输出 `aggregate.json` 与 `summary.md`。

本轮没有使用 `--promote`，因此即使出现 `promote` 决策也不会自动写入 active。

## 实验配置

### Coder block 验证

```bash
uv run python scripts/validate_candidate_blocks.py \
  --agent coder \
  --limit 1 \
  --max-iters 1 \
  --max-task-wall-time-s 120 \
  --command-timeout-s 300
```

输出目录：

```text
results/candidate_validation/block_validation_20260607_143700/
```

### Evaluator block 验证

```bash
uv run python scripts/validate_candidate_blocks.py \
  --agent evaluator \
  --limit 1 \
  --max-iters 1 \
  --max-task-wall-time-s 60 \
  --command-timeout-s 120
```

输出目录：

```text
results/candidate_validation/block_validation_20260607_144129/
```

## Coder Block 结果

| decision | count |
| --- | ---: |
| keep_candidate | 13 |
| reject | 1 |
| promote | 0 |

明细：

| block | decision | baseline solved | candidate solved | baseline ACPS | candidate ACPS |
| --- | --- | ---: | ---: | ---: | ---: |
| registered_round_robin_grant | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| registered_round_robin_grant | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_misc_hdl | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_arbiter | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_arbiter | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_counter | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_counter | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_fsm | reject | 0 | 0 | None | None |
| repair_pattern_sequential_fsm | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_register | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_register | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_shift | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_shift | keep_candidate | 1 | 1 | 1.0 | 1.0 |
| repair_pattern_sequential_shift | keep_candidate | 1 | 1 | 1.0 | 1.0 |

## Evaluator Block 结果

| decision | count |
| --- | ---: |
| pending | 14 |

原因：当前 evaluator skill 仍未接入 adversarial test generation。它们可以被保存为候选测试策略，但不能用 coder 通过率直接证明有效。

## 观察

### 1. 没有 block 达到 promote 条件

本轮 coder block 大多是 `keep_candidate`。主要原因不是它们一定无效，而是 validation task 在轻量配置下已经被 seed-only baseline 一次通过。

当前 promote 规则是：

- candidate solved 数更多；
- 或 solved 数相同但 ACPS-Iter 严格降低。

当 baseline 已经 `1/1` 且 `ACPS-Iter = 1.0` 时，candidate 不可能再严格降低。因此这类任务只能证明 candidate 没有退化，不能证明 candidate 有增益。

### 2. 一个 FSM block 被 reject

`repair_pattern_sequential_fsm` 中有一个 block 在 validation 上没有通过，且没有 ACPS 数据，因此被判为 `reject`。验证脚本将其复制到：

```text
skills/rejected/candidate_block.coder.repair_pattern_sequential_fsm.43e4ce22df583720.yaml
```

这说明 validation gate 正在发挥作用：不是所有自动生成的 skill 都会进入 active。

### 3. Validation 本身也会产生新 skill

本轮验证过程中，失败任务又产生了新的 candidate skill：

```text
skills/candidate/candidate.verilogeval_spec_to_rtl_prob107_fsm1s.coder.repair_pattern_sequential_fsm.1780814333.yaml
skills/candidate/candidate.verilogeval_spec_to_rtl_prob107_fsm1s.coder.repair_pattern_sequential_fsm.1780814348.yaml
skills/candidate/candidate.verilogeval_spec_to_rtl_prob107_fsm1s.evaluator.check_pattern_sequential_fsm.1780814333.yaml
skills/candidate/candidate.verilogeval_spec_to_rtl_prob107_fsm1s.evaluator.check_pattern_sequential_fsm.1780814348.yaml
```

这符合系统设计：失败本身就是完整信息，可以被 evaluator 记录，也可以反馈给 coder 形成下一轮 skill。

## 结论

本轮不能证明 candidate block 已经带来严格收益，但证明了三个关键点：

1. candidate block 批量 validation gate 已经可运行；
2. gate 能区分 `keep_candidate` 与 `reject`，不会盲目提升 skill；
3. evaluator block 仍处于不可验证状态，下一阶段必须接入 adversarial test generation。

因此，当前不能把 13 个 `keep_candidate` block 直接 promote 到 active。它们应该保留在 candidate store，等待更难 validation task 或重复实验来证明收益。

## 下一步实验建议

1. 对高频 block 做更强验证：
   - `sequential_register`
   - `sequential_counter`
   - `sequential_fsm`
   - `sequential_shift`

2. 将验证配置从 `limit=1, max_iters=1` 提升到：

```text
limit=2 或 3
max_iters=2
```

3. 构建“困难 validation subset”：
   - 选择 seed-only 不稳定或需要多次迭代的任务；
   - 避免 baseline 已经一次通过导致 ACPS 无法继续下降。

4. 优先实现 evaluator adversarial skill adapter，使 evaluator block 从 `pending` 变成可以实际生成测试的 skill。

