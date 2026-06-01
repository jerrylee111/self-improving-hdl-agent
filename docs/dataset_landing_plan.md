# HDL Agent 数据集落地方案

## 1. 为什么需要单独落地数据集

这个项目的研究目标是证明 skill cache 对 Verilog/SystemVerilog agent 有用。因此数据集不能只停留在“可以用 HDLBits/VerilogEval/RTLLM”这种描述上，而必须明确：

- 数据从哪里来。
- 是否能合法使用。
- 如何转换成统一任务格式。
- 如何切分 evolution/validation/test。
- 如何避免 benchmark leakage。
- 如何保证 evaluator 的测试不是虚假的。
- 如何记录每个任务的难度、领域标签和评测方式。

如果数据集不落地，后面的 Pass@K、ACPS、AST、cache hit rate 都没有稳定实验基础。

## 2. 数据集分层设计

建议使用四层数据集：

| 层级 | 名称 | 用途 | 是否进入论文主结果 |
| --- | --- | --- | --- |
| D0 | Local Seed Set | 本仓库自带的最小任务集，用于 smoke test、开发调试、CI | 否，只用于开发 |
| D1 | VerilogEval/HDLBits-style | 标准小中型 Verilog 生成任务，用于主要 pass-rate 实验 | 是 |
| D2 | RTLLM-style Design RTL | 更接近自然语言设计规格的模块级 RTL 任务 | 是，作为泛化测试 |
| D3 | Synthetic Mutation Set | 人工注入 bug 或变体任务，用于验证 skill evolution 和 evaluator 鲁棒性 | 是，作为消融/诊断实验 |

## 3. 推荐外部数据源

### 3.1 VerilogEval

VerilogEval 是最适合第一阶段主实验的数据集。它来自 VerilogEval 论文，包含 156 个从 HDLBits 改编的 Verilog 代码生成任务，并带有自动评测框架。

用途：

- 主通过率实验。
- `fixed prompt`、`semantic top-k`、`locality-aware cache` 的核心对比。
- 统计 Pass@1、Pass@K、ACPS、AST。

导入策略：

1. 固定使用某个 release/commit，记录 commit hash。
2. 将每个任务转换为本项目统一 YAML schema。
3. 保留原始 prompt、top module、测试文件和 golden/reference 信息。
4. 按 topic/family 切分，不做纯随机切分。

注意：

- VerilogEval 任务可能存在版本差异，建议后续优先使用官方 NVLabs 仓库或明确标注的 patched version。
- 如果使用 patched VerilogEval-v2，需要在论文中说明 patch 来源和改动范围。

### 3.2 RTLLM

RTLLM 更接近自然语言设计规格到 RTL 的任务。官方仓库描述其包含 29 个 design，每个 design 目录包含自然语言描述、testbench 和 verified RTL。

用途：

- 检查 agent 是否只适合 HDLBits-style 小题，还是能处理更真实的设计描述。
- 作为 out-of-family generalization set。

导入策略：

1. 每个 design 作为一个 task family。
2. `design_description.txt` 转成 prompt。
3. `testbench.v` 作为 evaluator 外部 oracle。
4. `verified_verilog.v` 只作为 golden，不进入 coder 上下文。

注意：

- RTLLM testbench 原始说明中使用 Synopsys VCS；本项目第一阶段使用 `iverilog/verilator`，因此需要记录哪些任务可直接迁移，哪些需要适配。

### 3.3 Local Seed Set

Local Seed Set 是我们自己维护的小任务集，放在 `benchmarks/tasks/local_seed/`。它的作用不是刷榜，而是让系统能稳定开发：

- 不依赖外部网络。
- 不依赖第三方 benchmark 格式。
- 任务规模小，方便调试 coder/evaluator/cache。
- 覆盖最常见 skill：组合逻辑、位宽、加法器、mux、寄存器、reset、edge detect、counter、FSM。

### 3.4 Synthetic Mutation Set

Mutation set 用于验证 evaluator 和 skill evolution：

- 对正确 RTL 注入常见 bug。
- 要求 evaluator 发现并定位问题。
- 或要求 coder 根据失败日志修复。

推荐 mutation 类型：

- reset 极性反了。
- 阻塞/非阻塞赋值错误。
- 位宽截断。
- signed/unsigned 错误。
- 漏 default 导致 latch。
- counter 终止条件 off-by-one。
- valid/ready 下 backpressure 处理错误。

## 4. 统一任务 Schema

每个任务转成 YAML：

```yaml
id: local_comb_and_gate
source: local_seed
license: project-owned
language: verilog
family: combinational_basic
tags: [combinational, boolean]
difficulty: 1
prompt: |
  Implement a module named top_module ...
top_module: top_module
ports:
  - {name: a, dir: input, width: 1}
  - {name: y, dir: output, width: 1}
clock: null
reset: null
expected:
  type: truth_table | reference_model | testbench | formal
  file: optional/path
evaluation:
  lint: true
  simulation: true
  formal: false
split:
  default: dev
```

关键原则：

- `prompt` 是 coder 能看的任务描述。
- `expected` 和 `evaluation` 是 evaluator/harness 用的，不应泄漏给 coder。
- `tags` 用于 skill cache 的空间局部性。
- `family` 用于数据切分，避免同族任务同时出现在 evolution 和 test。

## 5. 数据切分方案

不要简单随机切分。应该按任务 family 切分：

```text
evolution set:
  - local_seed/combinational_basic
  - verilogeval/simple_comb
  - verilogeval/simple_seq

validation set:
  - verilogeval/fsm_small
  - verilogeval/arithmetic

test set:
  - verilogeval/fsm_complex
  - verilogeval/datapath
  - rtllm/design_small

regression set:
  - local_seed/*
  - synthetic_mutation/*
```

这样可以减少同构题泄漏，避免 skill cache 只是记住某类 benchmark 模板。

## 6. 实验中每个任务必须记录的信息

每次运行任务，都要在 `results/*.jsonl` 中记录：

```json
{
  "task_id": "local_comb_and_gate",
  "source": "local_seed",
  "family": "combinational_basic",
  "tags": ["combinational", "boolean"],
  "policy": "locality_aware",
  "model": "deepseek-v4-pro",
  "skill_budget_tokens": 4096,
  "retrieved_skills": ["skill.comb.default_assignment.001"],
  "passed": true,
  "iterations": 1,
  "tool_calls": 2,
  "prompt_tokens": 1234,
  "completion_tokens": 456,
  "wall_time_s": 8.1,
  "failure_signature": null
}
```

这些字段可以直接计算：

- Pass@K。
- ACPS。
- AST。
- 每类任务上的 pass rate。
- 每类 skill 的 useful hit rate。
- 不同 cache policy 的消融结果。

## 7. 第一阶段落地步骤

### Step 1：完成 Local Seed Set

当前先落地 12 个本地任务，覆盖：

- 基础组合逻辑。
- mux。
- half/full adder。
- vector 操作。
- popcount。
- priority encoder。
- DFF/reset。
- edge detect。
- counter。
- 小 FSM。

### Step 2：实现 task schema 校验

`harness/task_schema.py` 负责：

- 读取 YAML。
- 校验必要字段。
- 校验 ports。
- 校验 tags/family/source。
- 为 cache fingerprint 提供结构化输入。

### Step 3：实现 dataset registry

`benchmarks/datasets.yaml` 负责登记：

- 本地数据集。
- 外部数据集来源 URL。
- license。
- commit/release。
- split 文件。

### Step 4：实现外部导入脚本

后续添加：

```text
scripts/import_verilogeval.py
scripts/import_rtllm.py
scripts/make_splits.py
```

导入脚本只做格式转换，不改 benchmark 原始语义。

## 8. 数据集使用顺序

推荐顺序：

1. 先用 Local Seed Set 打通系统。
2. 接入 VerilogEval 做第一轮主要实验。
3. 接入 RTLLM 做泛化测试。
4. 生成 Synthetic Mutation Set 做 evaluator 和 skill evolution 诊断。

这样可以防止系统还没跑通就陷入外部 benchmark 适配细节。

## 9. 论文中可以写的数据集说明

可以这样组织：

> We evaluate on four dataset tiers: a project-owned local seed set for infrastructure validation, VerilogEval-style tasks for standard functional correctness evaluation, RTLLM-style natural-language design tasks for out-of-family generalization, and synthetic mutation tasks for evaluator robustness and skill-evolution analysis. Dataset splits are made by task family rather than random instance-level sampling to reduce template leakage.

中文表述：

> 本文使用四层数据集：本地种子集用于系统验证，VerilogEval-style 任务用于标准功能正确性评测，RTLLM-style 任务用于跨任务族泛化评测，Synthetic Mutation Set 用于 evaluator 鲁棒性与 skill evolution 分析。所有切分按任务族进行，而不是按样本随机切分，以降低模板泄漏风险。

## 10. 资料来源

- [VerilogEval paper](https://arxiv.org/abs/2309.07544)：提出面向 Verilog 代码生成的自动评测 benchmark，包含 156 个 HDLBits-derived 任务。
- [NVLabs VerilogEval GitHub](https://github.com/NVlabs/verilog-eval)：VerilogEval 官方代码/数据来源。
- [RTLLM GitHub](https://github.com/hkust-zhiyao/RTLLM)：包含 29 个 design，每个 design 提供自然语言描述、testbench 和 verified RTL。
- [RTLLM paper](https://arxiv.org/abs/2308.05345)：提出自然语言到设计 RTL 的 benchmark。
- [VerilogEval-v2-NTU Hugging Face](https://huggingface.co/datasets/AS-SiliconMind/VerilogEval-v2-NTU)：提供 patched VerilogEval-v2 数据说明，可作为后续比较对象，但需要明确标注 patch 来源。
