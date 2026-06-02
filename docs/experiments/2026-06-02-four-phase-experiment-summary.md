# 四阶段实验汇总报告

日期：2026-06-02

## 实验目标

本轮实验按四个阶段推进，目标是同时观察 coder skill、evaluator skill 和 skill cache 的作用：

1. Arbiter 单任务消融：比较 active coder skill 和 evaluator 强度。
2. 同族迁移实验：观察 arbiter active skill 是否能迁移到相近任务。
3. Evaluator skill 收益实验：用 mutant kill rate 衡量 evaluator 找错能力。
4. Cache 策略实验：比较 `no_skill/fixed/tag_topk/locality_aware`。

本报告延续用户提出的核心原则：

> coder skill 的目标是写对代码；evaluator skill 的目标是证明代码是错的。

因此，下文中的通过均写作 `accepted_by_current_evaluator`，不等价于完整正确性证明。所有结果的 `correctness_claim` 仍是 `not_proven`。

## 阶段一：Arbiter 单任务消融

任务：

`benchmarks/tasks/local_seed/round_robin_arbiter2.yaml`

四组配置：

| 组别 | active coder skill | evaluator profile | accepted | iterations | wall_time_s | L1 loaded arbiter skill |
| --- | --- | --- | --- | ---: | ---: | --- |
| A | false | `basic` | true | 2 | 37.422 | false |
| B | true | `basic` | true | 2 | 51.032 | true |
| C | false | `adversarial_v2` | true | 2 | 164.707 | false |
| D | true | `adversarial_v2` | true | 2 | 45.032 | true |

观察：

- 四组都在 3 次以内被当前 evaluator 接受。
- basic evaluator 下，active skill 没有减少迭代数。
- adversarial evaluator 下，active skill 没有减少迭代数，但 wall time 从 164.707s 降到 45.032s。
- 由于这是单次 LLM 运行，wall time 受 API 和采样随机性影响，不能单独作为强结论。

阶段一结论：

active arbiter skill 在强 evaluator 下至少没有破坏结果，并且这次运行中显著降低了耗时；但迭代数没有改善，因此需要多次重复才能形成统计结论。

## 阶段二：同族迁移实验

新增任务：

`benchmarks/tasks/local_seed/round_robin_arbiter2_enable.yaml`

这个任务与原 arbiter 同属 `sequential_arbiter`，但多了 `enable` 语义：

- `enable=0` 时 `grant=0`。
- `enable=0` 时 priority 不应更新。
- `enable=1` 时执行正常 round-robin。

检索结果：

| active skills | selected skills |
| --- | --- |
| false | `skill.rtl.interface_exact.001`, `skill.rtl.seq_nonblocking.001`, `skill.rtl.comb_complete.001` |
| true | `skill.rtl.interface_exact.001`, `skill.rtl.arbiter.registered_round_robin_grant.001`, `skill.rtl.seq_nonblocking.001` |

运行结果：

| active coder skill | evaluator profile | accepted | iterations | wall_time_s | L1 loaded arbiter skill |
| --- | --- | --- | ---: | ---: | --- |
| false | `adversarial_v2` | true | 2 | 163.201 | false |
| true | `adversarial_v2` | true | 2 | 38.164 | true |

阶段二结论：

同族迁移的检索行为符合预期：active arbiter skill 会被 `round_robin_arbiter2_enable` 命中并加载进 L1。单次运行中，active skill 没有降低迭代数，但显著降低了 wall time。这个结果支持“问题局部性检索能把相关 skill 提进 L1”，但仍需要重复实验确认统计稳定性。

## 阶段三：Evaluator Skill 收益实验

实验报告：

`docs/experiments/2026-06-02-arbiter-mutant-evaluator-ablation.md`

命令：

```bash
uv run python -m experiments.run_mutant_eval \
  --out-dir results/mutant_eval_current
```

结果：

| evaluator | mutants | killed | survived | mutant_kill_rate | correct_accepted |
| --- | ---: | ---: | ---: | ---: | --- |
| `basic` | 6 | 4 | 2 | 0.6667 | true |
| `adversarial_v2` | 6 | 6 | 0 | 1.0000 | true |

旧 evaluator 漏掉的 mutant：

- `bug_reset_reentry_priority`
- `bug_stateful_single_request_inactive`

新 adversarial evaluator 全部杀掉，同时没有误杀 `correct_registered.v`。

阶段三结论：

这是本轮最强的正结果。它直接证明 evaluator skill v2 的价值不是“让代码通过”，而是“发现更多错误”：

```text
mutant_kill_rate: 0.6667 -> 1.0000
```

## 阶段四：Cache 策略实验

配置：

`experiments/configs/four_phase_cache_policy_small.yaml`

任务：

- `local_comb_mux2`
- `local_round_robin_arbiter2_enable`

策略：

- `no_skill`
- `fixed`
- `tag_topk`
- `locality_aware`

参数：

- `max_repair_iters = 2`
- `active_skills = true`
- `evaluator_profile = adversarial_v2`

命令：

```bash
DEEPSEEK_TIMEOUT_S=180 DEEPSEEK_MAX_RETRIES=1 \
uv run python -m experiments.run_experiment \
  experiments/configs/four_phase_cache_policy_small.yaml \
  --no-dry-run \
  --out-dir results/four_phase/phase4
```

### L1 Hit/Miss 修正

第一次阶段四实验暴露了一个 cache 机制问题：L1 hit 判断过宽，`interface` 这类 pinned/generic skill 会让后续任务误判为 hit，从而阻止 cache 对新任务进行 miss retrieval。

修正：

- pinned skill 不再单独构成 L1 hit。
- `sequential/reset/verilog` 这类泛化 term 不再单独构成 task-specific hit。
- 只有匹配 `arbiter/fairness/enable/family` 等更具体 task term 的 skill，才会阻止 miss。

修正后，同一个 L1 cache 从 `local_comb_mux2` 切到 `local_round_robin_arbiter2_enable` 时，会正确触发 miss，并重新加载 active arbiter skill。

汇总：

| metric | value |
| --- | ---: |
| tasks | 8 |
| solved / accepted | 5 |
| failed | 3 |
| api_failures | 0 |
| accepted_by_current_evaluator@2 | 0.625 |
| total_iterations | 11 |

逐项结果：

| policy | task | accepted | iterations | retrieved skill summary |
| --- | --- | --- | ---: | --- |
| `no_skill` | `local_comb_mux2` | true | 1 | none |
| `no_skill` | `local_round_robin_arbiter2_enable` | false | 2 | none |
| `fixed` | `local_comb_mux2` | true | 1 | seed fixed order |
| `fixed` | `local_round_robin_arbiter2_enable` | false | 2 | seed fixed order |
| `tag_topk` | `local_comb_mux2` | true | 1 | interface + comb + seq |
| `tag_topk` | `local_round_robin_arbiter2_enable` | false | 2 | interface + active arbiter + seq |
| `locality_aware` | `local_comb_mux2` | true | 1 | interface + seed set |
| `locality_aware` | `local_round_robin_arbiter2_enable` | true | 1 | active arbiter + seq + support skills |

重要发现：

- `no_skill` 和 `fixed` 无法在 2 轮内解决 `round_robin_arbiter2_enable`。
- `tag_topk` 检索到了 active arbiter skill，但仍未在 2 轮内被接受。
- `locality_aware` 在修正 L1 hit/miss 后重新加载 active arbiter skill，并在 1 轮内被当前 evaluator 接受。
- 这说明 cache hit/miss 的定义本身会显著影响策略实验结果。

阶段四结论：

阶段四给出了一个初步正结果：在这个小样本中，`locality_aware` 是唯一能在 `max_iters=2` 下通过两个任务的策略。它的优势来自两个因素：

1. L1 对新任务正确 miss。
2. miss 后把 active arbiter skill 放在 L1 前部。

但这仍是单次运行结果，受 LLM 采样影响。后续需要多 seed 重复。

## 总体结论

本轮四阶段实验全部已运行，结论如下：

1. Active coder skill 可以被 L1 cache 正确加载，并且在同族 arbiter 任务上被命中。
2. 单任务和迁移任务中，active skill 没有稳定降低迭代数，但在本次运行中显著降低了 wall time。
3. Evaluator skill 的增强效果最明确，`mutant_kill_rate` 从 0.6667 提升到 1.0000。
4. Cache 策略实验暴露并修复了 L1 hit/miss 判定问题；修复后 `locality_aware` 在小样本中表现最好。

当前最稳的论文证据是阶段三：

> evaluator skill 的目标是证明代码错误，而 mutation testing 能定量证明 evaluator skill 的找错能力提升。

当前最需要加强的是阶段四的统计稳定性：

> cache 策略已经出现初步正结果，但仍需要多任务、多 seed、多次运行，以及更好的 useful retrieval 指标。

## 后续建议

下一轮实验建议：

1. 对阶段一和阶段二做 `N=5` 重复，报告接受率和平均迭代数。
2. 对 `locality_aware` 和 `tag_topk` 做多 seed 重复，确认 locality-aware 的优势是否稳定。
3. 扩展 mutant testing 到 FSM、FIFO、valid-ready。
4. 将 `accepted_by_current_evaluator@k` 和 `mutant_kill_rate` 分开报告，分别衡量 coder 与 evaluator。
5. 引入 hidden evaluator 或独立 holdout tests，避免 coder 只学习当前 evaluator 的漏洞。
