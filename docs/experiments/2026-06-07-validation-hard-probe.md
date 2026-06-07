# Validation Hard Probe 实验

日期：2026-06-07

## 背景

上一轮 candidate block 批量验证中，大多数 coder block 得到 `keep_candidate`，没有任何 block 达到 `promote`。主要原因是 validation split 中被匹配到的任务过于容易：seed-only baseline 已经一次通过，candidate 很难在 solved count 或 ACPS-Iter 上继续严格提升。

本轮实验的目标是从 validation split 中挑出更可能暴露 skill 差异的任务，形成一个小型 `validation-hard-probe`。

## 配置

新增配置：

```text
experiments/configs/verilogeval_validation_hard_probe.yaml
```

任务选择规则：

- 只从 VerilogEval validation split 中选择；
- 优先选择 sequential counter/register/FSM/shift 类任务；
- 共 8 个任务。

运行命令：

```bash
uv run python experiments/run_taskset_ablation.py \
  experiments/configs/verilogeval_validation_hard_probe.yaml \
  --no-dry-run
```

输出目录：

```text
results/taskset_ablation/verilogeval_validation_hard_probe_20260607_144552/
```

## 结果

| condition | solved | pass@k | ACPS-Iter | L1 hit | candidates | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| validation_hard_no_skill | 8/8 | 1.0 | 1.0 | 0/8 | 0 | 0 |
| validation_hard_seed_only | 8/8 | 1.0 | 1.0 | 5/8 | 0 | 0 |
| validation_hard_active | 8/8 | 1.0 | 1.125 | 5/8 | 2 | 0 |

## 逐项观察

### 1. 当前 validation split 区分度仍然不足

即使只挑 sequential counter/register/FSM/shift 任务，`no_skill` 仍然 8/8 且全部一次通过。

这说明当前 validation split 对 DeepSeek 当前代码能力来说太容易，不能有效地区分：

- no-skill；
- seed-only；
- active-cache；
- candidate-cache。

因此，如果继续用这组 validation task 直接做 promote gate，会天然偏向 `keep_candidate`，很难观察到严格收益。

### 2. L1 hit 不等于 utility

seed-only 与 active 条件都有 `5/8` 的 L1 hit，但 pass@k 与 ACPS-Iter 没有优于 no-skill。

这说明后续论文指标不能只报告 L1 hit rate，还必须报告 hit 后的实际效用，例如：

- hit 后 solved 是否提升；
- hit 后 ACPS-Iter 是否下降；
- hit 后 wall time 是否变化；
- hit 后是否产生新的失败/candidate。

### 3. active 条件出现轻微退化信号

`validation_hard_active` 的 ACPS-Iter 为 `1.125`，高于 `no_skill` 和 `seed_only` 的 `1.0`。

具体来自 `verilogeval_spec_to_rtl_prob107_fsm1s`：

- no-skill：1 次迭代通过；
- seed-only：1 次迭代通过；
- active：2 次迭代通过，并生成 2 个 candidate skill。

不过需要谨慎解释：该任务在 seed-only 和 active 条件下命中的 L1 skill ids 相同：

```text
skill.rtl.seq_nonblocking.001
skill.rtl.interface_exact.001
skill.rtl.width_signedness.001
```

因此这次退化不能直接归因于 active skill，更可能是模型随机性或上下文轻微波动。它应该作为“需要重复实验确认的退化信号”，而不是结论。

## 工具修复

本轮发现直接运行以下脚本时会遇到 `ModuleNotFoundError: No module named 'agents'`：

- `experiments/run_taskset_ablation.py`
- `experiments/run_experiment.py`
- `scripts/validate_candidate_skill.py`
- `scripts/validate_candidate_blocks.py`

已为这些入口加入项目根目录 `sys.path` 注入。现在可以直接运行，不必手动写 `PYTHONPATH=$PWD`。

验证命令：

```bash
uv run python experiments/run_taskset_ablation.py \
  experiments/configs/verilogeval_validation_hard_probe.yaml \
  --dry-run

uv run python -m compileall \
  experiments/run_taskset_ablation.py \
  experiments/run_experiment.py \
  scripts/validate_candidate_skill.py \
  scripts/validate_candidate_blocks.py
```

## 追加：Stress Set 抽取工具

新增脚本：

```bash
uv run python scripts/build_hard_task_subset.py
```

该脚本从已有 `records.jsonl` 中按任务难度打分，打分因素包括：

- 是否失败；
- 是否超时；
- 是否需要多次迭代；
- 是否生成 candidate skill；
- wall time。

本轮基于 hard-timeout 版 `seq20` 的 seed-only 与 active 条件生成了一个 stress set：

```bash
uv run python scripts/build_hard_task_subset.py \
  results/taskset_ablation/verilogeval_seq20_cache_ablation_20260605_171144/records.jsonl \
  --conditions seq20_seed_only_locality,seq20_active_locality \
  --top-k 8 \
  --out-config experiments/configs/verilogeval_evolution_stress8_from_records.yaml \
  --name verilogeval_evolution_stress8_from_records
```

输出：

```text
experiments/configs/verilogeval_evolution_stress8_from_records.yaml
experiments/configs/verilogeval_evolution_stress8_from_records.manifest.json
```

选出的 stress tasks：

| task | family |
| --- | --- |
| verilogeval_spec_to_rtl_prob104_mt2015_muxdff | sequential_register |
| verilogeval_spec_to_rtl_prob082_lfsr32 | sequential_shift |
| verilogeval_spec_to_rtl_prob031_dff | sequential_register |
| verilogeval_spec_to_rtl_prob034_dff8 | sequential_register |
| verilogeval_spec_to_rtl_prob111_fsm2s | sequential_fsm |
| verilogeval_spec_to_rtl_prob096_review2015_fsmseq | sequential_fsm |
| verilogeval_spec_to_rtl_prob063_review2015_shiftcount | sequential_counter |
| verilogeval_spec_to_rtl_prob086_lfsr5 | sequential_shift |

注意：这个 stress set 来自 evolution split 的历史实验记录，因此适合做压力回归和检索策略调试，不适合作为最终 promote validation 或 holdout 证据。

## 结论

本轮实验不是一个正向收益实验，而是一个重要的实验设计修正：

1. 当前 VerilogEval validation split 中的 sequential 子集仍然太容易；
2. 不能继续用“随机匹配 validation task”作为 candidate promote 的主要证据；
3. 需要构造更强的 validation gate，尤其是让 evaluator 根据 skill 生成 adversarial test；
4. active-cache 的潜在退化需要重复实验和 leave-one-out 才能确认。

## 下一步

下一步应从两个方向推进：

1. 构造 hard validation set：
   - 从 evolution split 中只使用未参与某个 candidate block 生成的任务；
   - 或从 validation task 生成 adversarial variants；
   - 记录每个 task 的 baseline difficulty。

2. 实现 evaluator adversarial skill adapter：
   - evaluator skill 不再只是文本；
   - 它应能生成额外 test scenarios；
   - 让 evaluator block 从 `pending` 变成可验证对象。
