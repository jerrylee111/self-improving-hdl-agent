# 数据集自进化实验启动方案

日期：2026-06-02

## 用户提出的想法

用户提出：先准备一批数据集，让系统自己批量运行，随着失败和 evaluator 反馈自动生成 skill，再观察 skill cache 是否带来能力提升。同时用户指出，主要问题仍然是 evaluator 怎么找出错误，可能需要一开始给 evaluator 一套基础 skill。

这个判断是正确的。数据集可以批量落地，但不能直接把全部任务都用于 skill evolution，否则容易出现两个问题：

1. evaluator 太弱，系统学到的是“过弱测试”的技巧。
2. evolution/validation/test 混在一起，后续无法证明 skill 真的泛化。

## 数据集分层

本阶段采用三层：

| split | 用途 | 是否生成 skill |
| --- | --- | --- |
| evolution | 允许失败后生成 candidate skill | 是 |
| validation | 验证 candidate 是否能提升为 active | 否，只用于筛选 |
| holdout/test | 最终证明 skill cache 是否泛化 | 否 |

外部数据源先下载到：

`benchmarks/external/raw/`

该目录被 `.gitignore` 忽略；仓库只提交下载脚本、manifest 和导入脚本。

## 已准备的数据源

下载脚本：

`scripts/download_datasets.py`

计划下载：

- VerilogEval：标准 HDLBits-style 代码生成任务。
- RTLLM：自然语言 RTL design 任务。

命令：

```bash
uv run python scripts/download_datasets.py
```

脚本会记录每个外部仓库的 commit hash，保证后续论文实验可复现。

## Evaluator 初始基础 Skill

为了避免系统一开始就被弱 evaluator 带偏，evaluator 应从一组基础 adversarial skill 开始。这些 skill 不包含任何任务答案，只包含找错原则：

- reset：同步/异步 reset、reset re-entry、reset 后状态清空。
- FSM：overlap pattern、false positive、one-cycle pulse、非法状态恢复。
- arbiter：grant onehot0、grant subset req、both-request fairness、idle grant zero。
- valid-ready：backpressure 下 data stable、valid stable、ready 不能错误拉高、同周期 drain+accept。
- FIFO：full/empty 边界、wrap pointer、simultaneous read/write。
- arithmetic：位宽截断、carry/overflow、signed/unsigned。

这些基础 skill 的目标是让 evaluator 尽早发现反例，而不是让 coder 更容易过测试。

## 自进化运行流程

```text
external dataset
  -> import task yaml
  -> evolution split
  -> coder generates RTL
  -> evaluator tries to break RTL
  -> failure creates coder/evaluator candidate skill
  -> validation split checks candidate
  -> promoted active skill enters external store
  -> L1 cache retrieves active skill for similar tasks
  -> holdout split measures generalization
```

## 当前风险

1. 外部 benchmark 的 testbench 可能依赖 VCS 或特定工具，需要适配到 iverilog/verilator。
2. VerilogEval/RTLLM 的任务格式不同，导入时不能把 golden RTL 泄露给 coder。
3. API failure 必须从 HDL failure 中分离，否则 skill evolution 会被噪声污染。
4. candidate skill 现在会重复生成，需要后续加入去重和合并。
5. evaluator 基础 skill 需要单独验证，否则 evaluator 自己也可能误杀正确设计。

## 下一步

1. 下载 VerilogEval 和 RTLLM 原始仓库。
2. 写 import 脚本，把可运行任务转换为统一 YAML。
3. 建立 evolution/validation/holdout split。
4. 添加 evaluator base skill seed。
5. 先跑 20-30 个 evolution 任务，观察 candidate skill 生成质量。

## 2026-06-02 进展记录

本轮已经把“先准备一批数据集，让系统自己跑，生成 skill”的想法落成了第一版可执行链路。

已完成：

- 下载 VerilogEval 和 RTLLM 原始仓库，记录原始 commit。
- 新增 `scripts/import_verilogeval.py`，把 VerilogEval `dataset_spec-to-rtl` 导入为统一任务 YAML。
- 当前导入 120 个 VerilogEval 任务：
  - evolution：72
  - validation：24
  - holdout：24
- evaluator 已支持外部数据集自带 testbench/reference module。
- 对 VerilogEval testbench 做了最小预处理，移除 `$dumpfile/$dumpvars`，避免 Icarus 因波形信号声明顺序报错；验证逻辑不改。
- 新增两个实验配置：
  - `experiments/configs/verilogeval_evolution_smoke.yaml`
  - `experiments/configs/verilogeval_hard_smoke.yaml`

## 外部数据集 Smoke 结果

### 简单 evolution smoke

配置：`experiments/configs/verilogeval_evolution_smoke.yaml`

结果目录：`results/verilogeval_smoke/verilogeval_evolution_smoke_20260602_221025/`

结果：

| 指标 | 数值 |
| --- | --- |
| tasks | 6 |
| solved | 6 |
| pass@k | 1.0 |
| total iterations | 6 |
| ACPS-Iter | 1.0 |
| AST-Iter | 1.0 |
| API failures | 0 |

结论：这组任务证明外部 testbench 接入是可运行的，但题目偏简单，没有触发失败，因此没有自然生成 candidate skill。

### hard smoke

配置：`experiments/configs/verilogeval_hard_smoke.yaml`

结果目录：`results/verilogeval_smoke/verilogeval_hard_smoke_20260602_221208/`

结果：

| 指标 | 数值 |
| --- | --- |
| tasks | 4 |
| solved | 4 |
| pass@k | 1.0 |
| total iterations | 5 |
| ACPS-Iter | 1.25 |
| AST-Iter | 0.8 |
| API failures | 0 |

逐题观察：

| task | pass | iterations | wall time |
| --- | --- | --- | --- |
| `Prob035_count1to10` | true | 1 | 11.748s |
| `Prob063_review2015_shiftcount` | true | 2 | 84.375s |
| `Prob082_lfsr32` | true | 1 | 207.318s |
| `Prob084_ece241_2013_q12` | true | 1 | 46.358s |

`Prob063_review2015_shiftcount` 在第一次失败后第二次通过，触发了 coder/evaluator candidate skill 生成：

- `candidate.verilogeval_spec_to_rtl_prob063_review2015_shiftcount.coder.repair_pattern_sequential_counter.1780409624`
- `candidate.verilogeval_spec_to_rtl_prob063_review2015_shiftcount.evaluator.check_pattern_sequential_counter.1780409624`

随后改进了 skill mining，使其不再只生成模板化描述，而是抽取结构化失败信息。基于同一失败重新生成的 candidate 为：

- `candidate.verilogeval_spec_to_rtl_prob063_review2015_shiftcount.coder.repair_pattern_sequential_counter.1780409950`
- `candidate.verilogeval_spec_to_rtl_prob063_review2015_shiftcount.evaluator.check_pattern_sequential_counter.1780409950`

新的 payload 明确记录：

- output：`q`
- mismatches：1886 / 2071 samples
- first mismatch time：10
- coder 关注：reset value、posedge update order、nonblocking assignments、enable conditions、terminal-count behavior、current-state/next-state 输出关系。
- evaluator 关注：reset release、first active cycle、terminal-count/wrap cycles、consecutive enabled cycles，并逐周期对比 reference model。

## 对用户观点的回应

用户提出“主要问题还是 evaluator 怎么去找出错误，可能的方式应该是通过开头给一个基础的 skill”。本轮结果支持这个判断：

1. 数据集导入后，系统确实可以自动跑并从失败中生成 skill。
2. 但如果 evaluator 只依赖数据集 testbench，skill 会围绕已有测试暴露的错误生成，仍然可能学不到隐藏 bug。
3. 因此 evaluator base skill 应该作为初始 L1/seed 的一部分，目标不是帮助 coder 写代码，而是指导 evaluator 主动找反例。
4. 对外部数据集实验来说，后续需要把“数据集自带 testbench”和“evaluator adversarial skill 生成的补充测试”分开记录，才能证明 evaluator 不只是复述 benchmark。

## 新暴露的问题

1. VerilogEval 入门和中等题对当前模型偏简单，pass@k 很容易到 1.0；要观察 skill evolution，需要选择更难任务或主动引入 mutant/hidden adversarial tests。
2. LFSR 单题耗时 207s，自动批跑必须增加 per-task timeout、skip 和恢复机制。
3. candidate skill 已经能生成，但还缺 validation gate：不能因为一次失败就提升为 active。
4. 需要去重/合并 candidate，否则相似失败会产生大量重复文件。

## 下一轮建议

1. 实现 candidate validation gate：candidate 只在 validation split 上提升指标后才能进入 `skills/active/`。
2. 给 runner 增加 per-task wall-time budget，记录 timeout rate。
3. 在 VerilogEval evolution 中挑 FSM/LFSR/shift/counter 子集，跑 N=20。
4. 对同一批任务做 no-skill、seed-only、active-cache 三组 ablation。
5. 在 evaluator 侧加入基于基础 skill 的补充 adversarial test 生成，并单独统计“自带 testbench pass，但 adversarial evaluator fail”的比例。

## 2026-06-02 追加进展：Validation Gate

本轮继续实现了 candidate skill 的验证闸门。

新增脚本：

`scripts/validate_candidate_skill.py`

它的流程是：

```text
candidate skill
  -> 从 validation split 选择同 family/tag 的任务
  -> seed-only baseline
  -> seed + candidate condition
  -> 比较 solved、ACPS-Iter、timeout、API failure
  -> 只有严格改善才允许 promote
```

当前自动提升规则：

规则版本：`strict_improvement_v1`

| 条件 | 决策 |
| --- | --- |
| candidate solved 数量高于 baseline | promote |
| solved 相同但 ACPS-Iter 严格降低 | promote |
| solved 相同且 ACPS-Iter 不变 | keep_candidate |
| 指标退化 | reject |
| evaluator candidate 尚未接入测试生成器 | pending |

这比“只要不退化就提升”更严格。原因是：如果 baseline 本来就一轮通过，那么 candidate 没有提供可测收益，直接提升会污染 active skill store。

### Shift-count Candidate 验证结果

验证对象：

`skills/candidate/candidate.verilogeval_spec_to_rtl_prob063_review2015_shiftcount.coder.repair_pattern_sequential_counter.1780409950.yaml`

结果：

| 条件 | tasks | solved | total iterations | ACPS-Iter | decision |
| --- | --- | --- | --- | --- | --- |
| seed-only baseline | 1 | 1 | 1 | 1.0 | - |
| seed + candidate | 1 | 1 | 1 | 1.0 | keep_candidate |

结论：该 candidate 记录了有价值的失败信息，但在当前 validation 任务上没有带来严格收益，因此不提升为 active。

对应 evaluator candidate：

`skills/candidate/candidate.verilogeval_spec_to_rtl_prob063_review2015_shiftcount.evaluator.check_pattern_sequential_counter.1780409950.yaml`

决策为 `pending`。原因是当前 evaluator skill 还没有真正接入 testbench/adversarial stimulus 生成器，不能用通过率验证它的效果。

### Timeout 记录

runner 和实验入口已加入：

`max_task_wall_time_s`

summary 中新增：

`timeouts`

注意：当前 timeout 是协作式的，能阻止一个任务在多次 repair 中无限继续，但不能强行中断正在等待的单次 LLM 调用。后续如果要跑大批量，应进一步改成 per-task subprocess runner。
