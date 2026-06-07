# 下一轮实验报告：多族 Mutant Kill 与重复 Ablation

日期：2026-06-02

## 实验目标

本轮按上一份四阶段报告的后续建议继续推进：

1. 将 evaluator mutation testing 从 arbiter 扩展到 FSM 和 valid-ready。
2. 对关键 ablation 条件做 `N=5` 重复实验，观察 active skill 和 cache policy 的稳定性。
3. 继续记录用户提出的核心原则：evaluator skill 的目标是证明代码错误，因此必须报告找错能力和 API failure 过滤后的有效样本。

## 一、多任务族 Mutant Kill

新增 mutant 数据集：

- `benchmarks/mutants/fsm_101_detector/`
- `benchmarks/mutants/valid_ready_skid/`

同时保留前一轮 arbiter mutant 数据集：

- `benchmarks/mutants/round_robin_arbiter2/`

运行命令示例：

```bash
uv run python -m experiments.run_mutant_eval \
  --mutants-dir benchmarks/mutants/fsm_101_detector \
  --task benchmarks/tasks/local_seed/fsm_101_detector.yaml \
  --out-dir results/next_round/mutant_eval
```

### 结果汇总

| task family | basic kill rate | adversarial_v2 kill rate | correct accepted |
| --- | ---: | ---: | --- |
| round-robin arbiter | 0.6667 | 1.0000 | true |
| FSM 101 detector | 0.3333 | 1.0000 | true |
| valid-ready skid buffer | 0.0000 | 1.0000 | true |

### 解释

FSM 初次扩展时，`adversarial_v2` 误杀了正确设计。原因不是 coder RTL 错，而是 evaluator reference model 在 reset 周期仍然按输入历史计算期望值。这说明 evaluator 本身也需要验证。

修正后：

- reset 周期清空 testbench 内部 reference history。
- 增加 reset re-entry 反例：在 reset 前制造 `10` 历史后缀，reset 后输入 `1` 不应产生假阳性。

修正后的 FSM 结果为：

```text
basic:          mutant_kill_rate = 0.3333
adversarial_v2: mutant_kill_rate = 1.0000
correct_accepted = true
```

这一点很重要：evaluator skill 的演化也会犯错，mutation testing 不仅能评估 coder，也能暴露 evaluator 的错误规格实现。

## 二、N=5 重复 Ablation

新增脚本：

`experiments/run_repeated_task_ablation.py`

新增配置：

`experiments/configs/next_round_repeated_key_ablation.yaml`

运行命令：

```bash
uv run python -m experiments.run_repeated_task_ablation \
  experiments/configs/next_round_repeated_key_ablation.yaml \
  --repeats 5 \
  --out-dir results/next_round/repeated_ablation
```

结果文件：

`results/next_round/repeated_ablation/next_round_repeated_key_ablation_20260602_164525/summary.json`

### Raw 结果

| condition | accepted | raw rate | API failures | mean iter accepted |
| --- | ---: | ---: | ---: | ---: |
| `rr_no_active_tag_topk_adv` | 4/5 | 0.8000 | 0 | 3.0 |
| `rr_active_tag_topk_adv` | 0/5 | 0.0000 | 5 | n/a |
| `enable_no_active_tag_topk_adv` | 1/5 | 0.2000 | 4 | 3.0 |
| `enable_active_tag_topk_adv` | 5/5 | 1.0000 | 0 | 2.0 |
| `enable_active_locality_adv` | 5/5 | 1.0000 | 0 | 1.8 |

### 过滤 API Failure 后

| condition | effective accepted | effective rate | 说明 |
| --- | ---: | ---: | --- |
| `rr_no_active_tag_topk_adv` | 4/5 | 0.8000 | 有效 HDL 样本完整 |
| `rr_active_tag_topk_adv` | 0/0 | n/a | 5 次均为 API failure，不能判定 |
| `enable_no_active_tag_topk_adv` | 1/1 | 1.0000 | 只有 1 个有效样本，统计不足 |
| `enable_active_tag_topk_adv` | 5/5 | 1.0000 | 有效 HDL 样本完整 |
| `enable_active_locality_adv` | 5/5 | 1.0000 | 有效 HDL 样本完整 |

## 三、关键观察

1. 多任务族 mutation testing 给出稳定正结果：
   - arbiter、FSM、valid-ready 三个任务族中，`adversarial_v2` 都达到 1.0000 kill rate。
   - 三个任务族的 correct design 均被接受。

2. 重复 ablation 中 API failure 仍然是主要干扰：
   - `rr_active_tag_topk_adv` 5 次全部是 LLM call failure，不能作为 skill 负结果。
   - `enable_no_active_tag_topk_adv` 只有 1 个有效 HDL 样本，因此不能和 active 组直接做强统计比较。

3. 对 enable arbiter，active skill 条件表现稳定：
   - `enable_active_tag_topk_adv`: 5/5 accepted，平均 2.0 次迭代。
   - `enable_active_locality_adv`: 5/5 accepted，平均 1.8 次迭代。

4. locality-aware 有轻微迭代优势：
   - 同样在 active enable arbiter 上，locality-aware 比 tag_topk 平均少 0.2 次迭代。
   - 样本量仍小，不能夸大结论，但方向符合 cache 局部性假设。

## 四、结论

本轮最可靠的结论仍然来自 evaluator mutation testing：

> evaluator skill 可以通过 adversarial tests 和 invariants 显著提升找错能力，并且这个提升可以用 mutant_kill_rate 定量观察。

本轮对 cache/coder skill 的结论更谨慎：

> active arbiter skill 在 enable arbiter 上表现稳定，5/5 有效样本被当前 evaluator 接受；locality-aware 比 tag_topk 略少迭代。但由于部分对照组 API failure 太多，还需要补跑 clean samples。

## 下一步

1. 补跑 API failure 污染的条件：
   - `rr_active_tag_topk_adv`
   - `enable_no_active_tag_topk_adv`

2. 给 repeated ablation summary 增加：
   - `effective_runs`
   - `effective_accepted_rate`
   - `api_failure_rate`

3. 扩展 evaluator skill：
   - FSM：更多 reset、overlap、false positive mutant。
   - valid-ready：同周期 drain+accept、back-to-back throughput、reset during backpressure。
   - FIFO：full/empty、wrap pointer、simultaneous read/write。

4. 引入独立 holdout evaluator，避免 coder 和 evaluator 共同过拟合当前 testbench。
