# Verilog/SystemVerilog 自进化 Coder/Evaluator Agent 研究与实现方案

## 1. 研究目标

我们要构建两个协作的硬件代码 agent：

- `coder`：负责生成、修改、修复 Verilog/SystemVerilog RTL 代码。
- `evaluator`：负责构建测试平台、运行仿真/形式验证/lint、诊断失败原因，并给出结构化反馈。

本项目的核心研究点不是简单证明“大模型可以写 HDL 代码”，而是证明：

> 在模型上下文有限、skill 总量超过上下文窗口时，一个规范化、外部化、类似计算机缓存的 skill memory，可以让 agent 更稳定地获得领域能力，并在 HDL 代码生成任务上带来可测量的性能提升。

工作假设：

> 当 skill memory 超出模型上下文窗口时，基于时间局部性和问题空间局部性的缓存策略，比纯提示词、固定 skill、或朴素 semantic top-k 检索更能选出有用 skill，从而提高通过率、减少修复轮数、降低 token 成本，并增强跨任务泛化能力。

## 2. 系统总览

系统分为四层：

1. 任务层：解析 HDL 任务描述、约束、接口、期望行为和已有测试。
2. Agent 层：`coder` 和 `evaluator` 形成闭环协作。
3. Skill cache 层：决定当前任务和当前迭代应该把哪些 skill 放入上下文。
4. 外部 skill store：持久化、版本化、可检索地保存所有演化出的 skill。

推荐工作流：

```text
任务输入 -> 任务指纹提取 -> skill cache 查询
        -> coder 生成候选 RTL
        -> evaluator 生成/运行检查
        -> 失败分析
        -> coder 修复
        -> 得到最终结果
        -> 生成 skill 演化候选
        -> evaluator 验证新增/更新 skill
        -> 将有效 skill 提交到外部存储
```

## 3. Agent 职责设计

### 3.1 Coder Agent

输入：

- 任务说明。
- 模块接口签名。
- 当前检索到的 coder skill。
- 上一轮 evaluator 的反馈。
- 项目风格和综合约束。

输出：

- RTL 文件。
- 必要的设计假设说明。
- 结构化自检清单。

核心能力：

- 判断任务是组合逻辑、时序逻辑、状态机、协议逻辑还是数据通路逻辑。
- 严格保持模块名、端口名、端口方向、位宽、reset 语义不变。
- 避免不可综合结构，除非任务明确允许测试平台代码。
- 根据仿真、lint、形式验证的反例进行修复。
- 失败后尽量做最小修改，而不是整段重写。

### 3.2 Evaluator Agent

输入：

- 任务说明。
- 候选 RTL。
- 当前检索到的 evaluator skill。
- 已有测试，如果有。

输出：

- testbench 文件。
- 工具运行结果。
- 结构化 verdict。
- 失败定位。
- 给 coder 的修复建议。

Evaluator 应该进行多层检查：

- 语法和 lint：例如 `verilator --lint-only`、`iverilog`、`svlint`。
- 动态仿真：生成 directed tests 和 randomized tests。
- 参考模型对比：如果能从任务中构造 Python/spec model，则用参考模型做 scoreboard。
- 形式验证：对适合的小模块使用 SymbiYosys/Yosys/property check。
- 鲁棒性检查：覆盖 reset、溢出、有符号/无符号、阻塞/非阻塞赋值、锁存器推断、握手协议时序等常见问题。

## 4. Skill 规范化设计

Skill 必须规范化。可以把一个 skill 看作“缓存行”：它不只是文本，还包含元数据、payload、验证状态和替换策略所需的统计信息。

建议 schema：

```yaml
id: skill.uuid
name: 简短的人类可读名称
agent: coder | evaluator | both
domain:
  language: verilog | systemverilog
  topic:
    - fsm
    - handshake
    - fifo
    - arithmetic
    - testbench
    - formal
    - reset
task_patterns:
  - "valid/ready protocol"
  - "synchronous reset"
preconditions:
  - "clocked design"
  - "single clock domain"
anti_patterns:
  - "do not use #delay in synthesizable RTL"
payload:
  type: rule | checklist | template | repair_pattern | test_strategy | counterexample
  content: |
    实际 skill 内容。
examples:
  positive:
    - task_id: ...
  negative:
    - task_id: ...
metrics:
  uses: 0
  successes: 0
  failures: 0
  utility_ema: 0.0
  token_cost_ema: 0.0
cache:
  created_at: ...
  last_used_at: ...
  last_success_at: ...
  ttl: optional
  pin: false
version:
  parent_ids: []
  revision: 1
  status: candidate | active | deprecated | rejected
validation:
  evidence:
    - benchmark: ...
      delta_pass_rate: ...
      delta_tokens: ...
```

Payload 应该短、可操作、可验证。坏 skill 是：

> 写 FSM 时要小心。

好 skill 是：

> 对同步 reset 的 one-hot FSM，在组合逻辑块开头给 next-state 和输出默认值；case 必须包含 default 分支并回到 reset state；不要在组合逻辑中直接赋值 state。

## 5. Skill 类型

不要把所有经验都堆成一个巨大 prompt library。应该把 skill 分成不同类型：

- 规则型 skill：简洁的约束或不变量。
- 清单型 skill：有顺序的设计/验证 checklist。
- 模板型 skill：可复用的 RTL/testbench 骨架。
- 修复型 skill：把失败特征映射到修复策略。
- 反例型 skill：保存过去的 bug 模式以及失败原因。
- 工具型 skill：记录某个工具如何调用、如何解释输出。
- 概念型 skill：解释协议语义或硬件概念。

为了节省上下文，大例子和小规则要分开存储。Cache 应该优先取压缩后的规则；只有预算允许或任务需要时，再取完整示例。

## 6. Skill Cache 设计

### 6.1 外部存储

建议使用混合存储：

- SQLite/Postgres：保存结构化元数据、版本、使用统计、实验日志。
- 向量索引：用于基于任务模式、payload 摘要、失败签名的语义检索。
- 文件/对象存储：保存较长 payload、示例、trace、生成产物。

最小实现可以使用：

- `skills/*.yaml` 作为 skill 源文件。
- SQLite 保存 metrics。
- FAISS/Chroma/LanceDB 保存 embedding 索引。

### 6.2 缓存层级

借鉴多级缓存结构：

- L0 prompt core：极小的永久规则，每次都放入上下文。
- L1 task cache：针对当前任务选择的 skill。
- L2 episode cache：同一任务多轮修复中持续保留的 skill。
- L3 external store：所有 active/candidate skill。

L0 只应该包含 HDL 任务中几乎永远有用的规则：

- 严格保持接口不变。
- 区分组合逻辑和时序逻辑。
- 时钟触发 always block 使用非阻塞赋值。
- 组合逻辑中必须完整赋值，避免 latch。
- 严格遵守 reset 极性和同步/异步语义。
- 最终提交前必须经过 evaluator。

### 6.3 映射机制

一个任务通过 task fingerprint 映射到候选 skill：

```json
{
  "language": "systemverilog",
  "constructs": ["fsm", "valid_ready", "fifo"],
  "signals": ["clk", "rst_n", "valid", "ready"],
  "semantics": ["backpressure", "single_clock"],
  "risk_tags": ["off_by_one", "reset", "throughput"],
  "tool_failures": ["verilator_width_warning"]
}
```

映射阶段：

1. 静态解析：提取端口、时钟、reset、关键词、协议信号。
2. LLM 分类器：用严格 JSON schema 生成 topic/risk tags。
3. Embedding 检索：基于任务描述和失败日志取语义 top-k。
4. 图扩展：根据 prerequisite、co-success、repairs-failure 等关系拉取邻近 skill。
5. Policy 打分：决定哪些 skill 真正进入上下文。

### 6.4 缓存准入策略

不是所有检索到的 skill 都应该进入上下文。一个 skill 进入缓存，需要满足：

- 与当前 task fingerprint 匹配。
- 在相似任务上有正向历史收益。
- 不与已选 skill 高度重复。
- token 成本与预期收益匹配。

准入打分可以定义为：

```text
score = alpha * semantic_similarity
      + beta  * topic_overlap
      + gamma * utility_ema
      + delta * recency
      + eta   * co_success_with_selected_skills
      - lambda * token_cost
      - rho    * redundancy
```

### 6.5 缓存替换策略

由于上下文有限，驱逐策略不应该只用 LRU，而应该根据“预期边际收益”驱逐。

推荐策略：locality-aware GreedyDual-Size with utility。

```text
priority(skill) =
  estimated_utility / token_cost
  + recency_bonus
  + locality_bonus
  + pinned_bonus
  - redundancy_penalty
```

当上下文超预算时，优先驱逐 priority 最低的 skill。

需要对比的替换/检索策略：

- 无 skill memory。
- 固定 expert prompt。
- Semantic top-k。
- LRU。
- LFU。
- Utility-only。
- 本文提出的 locality-aware utility cache。

### 6.6 空间局部性定义

在本项目里，空间局部性不是内存地址相邻，而是“问题局部性”：

- 同一 HDL 主题：FIFO、FSM、arbiter、ALU、CDC、handshake。
- 同一信号模式：`valid/ready`、`req/ack`、`clk/rst_n`。
- 同一失败类型：位宽错误、锁存器推断、reset bug、阻塞赋值 bug。
- 同一验证策略：参考模型、assertion、constrained random。
- 同一 benchmark family：HDLBits、VerilogEval、自定义 FIFO 任务等。

建议构建 skill graph：

```text
skill A --prerequisite--> skill B
skill A --co_success--> skill C
skill A --conflicts_with--> skill D
skill A --repairs_failure--> failure signature F
```

图扩展就是 skill cache 中的“空间预取”。

## 7. Skill 自动演化

Skill 演化必须有门控机制，不能让每次成功或失败都直接修改主 skill store。

### 7.1 候选 skill 生成

每个任务结束后，可以从以下信息中生成 candidate skill：

- 重复出现的错误。
- 成功修复步骤。
- Evaluator 发现的关键问题。
- 工具诊断信息。
- 人类确认过的经验。

候选生成时必须回答：

- 这次学到的可复用经验是什么？
- 未来什么任务应该触发它？
- 什么任务不应该触发它？
- 有什么证据支持它？
- 它会消耗多少 token？

### 7.2 Skill 验证

Candidate skill 进入 active 之前，需要经过验证：

1. 在小规模验证集上做 A/B test。
2. 在无关任务族上检查是否产生回归。
3. 比较 pass rate、迭代次数、token 成本和运行时间。
4. 拒绝模糊、重复、有害、过长的 skill。

Skill 状态：

- `candidate`：生成但未被信任。
- `active`：通过验证，可以被缓存检索。
- `deprecated`：被更好的版本替代。
- `rejected`：被证明有害或无用。

### 7.3 Skill 压缩

当 skill 规模越来越大时，需要做压缩：

- 合并重复 skill。
- 把混合 skill 拆成原子 skill。
- 将长示例总结为短规则。
- 完整 trace 放在外部，只在需要时检索。
- 将高收益 skill cluster 蒸馏成更短的 L0/L1 规则。

## 8. Coder/Evaluator 通信协议

两个 agent 之间应该使用结构化消息，而不是自由文本互相聊天。

Coder 输出格式：

```json
{
  "files": [{"path": "design.sv", "content": "..."}],
  "assumptions": ["..."],
  "self_checks": ["..."],
  "skills_used": ["skill.reset.sync.001"]
}
```

Evaluator 输出格式：

```json
{
  "verdict": "pass | fail | inconclusive",
  "tool_results": [{"tool": "verilator", "status": "fail", "summary": "..."}],
  "failed_cases": [{"name": "...", "trace": "..."}],
  "suspected_causes": ["..."],
  "repair_hints": ["..."],
  "skills_used": ["skill.tb.random.003"]
}
```

Evaluator 不能只说“错了”。它必须给出可操作的失败定位和修复提示。

## 9. 实现路线图

### Phase 0：Benchmark 和 Harness

定义统一任务格式：

```yaml
id: hdlbits_fsm_001
language: verilog
prompt: ...
top_module: top_module
ports:
  - {name: clk, dir: input, width: 1}
  - {name: reset, dir: input, width: 1}
expected:
  type: hidden_tests | reference_model | formal_properties
tags: [fsm, reset, sequential]
```

构建 harness：

- 生成候选代码文件。
- 运行 lint。
- 运行 testbench。
- 收集日志。
- 计算 pass/fail。

### Phase 1：Baseline Agents

先实现固定 prompt、无演化缓存的 `coder` 和 `evaluator`。

记录指标：

- Pass@1。
- N 轮修复后的通过率。
- 平均修复轮数。
- ACPS，即每解决一个任务所需的平均 agent 成本。
- Token 使用量。
- 墙钟时间。
- 语法错误率。

### Phase 2：外部 Skill Store

实现 YAML/JSON skill、检索逻辑和手写种子 skill。

种子 skill 应覆盖：

- 组合逻辑 always block 完整赋值。
- 时序逻辑非阻塞赋值。
- reset 极性和同步/异步语义。
- 位宽和符号扩展。
- FSM next-state 纪律。
- valid/ready 握手规则。
- testbench clock/reset 生成。
- scoreboard/reference-model 测试。
- 常见 Verilator 诊断解释。

### Phase 3：Skill Cache

实现：

- Task fingerprinting。
- 候选 skill 检索。
- 准入策略。
- 上下文预算打包。
- 驱逐策略。
- Skill 使用日志。

### Phase 4：自动演化

实现：

- 任务结束后的 skill mining。
- Candidate skill 验证。
- 版本管理和回滚。
- 基于 benchmark 子集的回归测试。

### Phase 5：研究评估

在不同 baseline 和 cache policy 上做受控实验。

## 10. 论文式实验设计

### 10.1 研究问题

RQ1：在固定上下文预算下，外部 skill memory 是否能提升 HDL 任务通过率？

RQ2：本文提出的缓存策略是否优于朴素 semantic top-k 检索？

RQ3：自动 skill 演化是否能随时间提升性能，同时不引入明显回归？

RQ4：哪种局部性信号最重要：最近使用、主题相似、失败类型相似，还是 co-success 图关系？

### 10.2 数据集

使用多个任务来源：

- HDLBits 风格任务。
- VerilogEval。
- RTLLM benchmark，如果 license 和环境允许。
- 自定义生成任务：FIFO、FSM、arbiter、ALU、counter、serializer。
- 注入已知 bug 类型的 mutation tasks。

划分方式应按任务族划分，而不是只做随机划分：

- Evolution set：用于 skill 演化。
- In-family validation set：同族验证。
- Out-of-family generalization set：跨族泛化测试。
- Regression set：长期回归测试。

### 10.3 Baseline

至少比较：

1. 无 skill 的基础 LLM agent。
2. 固定 expert prompt。
3. 全量 skill dump，直到上下文上限。
4. Semantic top-k retrieval。
5. LRU cache。
6. LFU cache。
7. Utility-only retrieval。
8. 本文提出的 locality-aware skill cache。

### 10.4 指标

主要指标：

- Pass@1。
- Pass@K repair iterations。
- Hidden-test pass rate。
- 适用任务上的 formal property pass rate。

效率指标：

- 每个 solved task 的 token 消耗。
- 每个 solved task 的工具调用次数。
- 墙钟时间。
- 修复迭代次数。
- ACPS：Average Cost Per Solved task，类似处理器中的 CPI，用于衡量“解决一个任务平均需要多少 agent 周期/成本”。
- AST：Agent Solution Throughput，类似 IPC，是 ACPS 的倒数，用于衡量单位 agent 成本能解决多少任务。

质量指标：

- 语法错误率。
- latch inference rate。
- width warning rate。
- reset bug rate。
- evaluator false-pass/false-fail rate。

Memory/cache 指标：

- Cache hit rate。
- Useful hit rate：检索到的 skill 是否被成功使用，或通过 ablation 证明有贡献。
- Skill pollution rate：active skill 后续被证明有害的比例。
- Eviction regret：被驱逐 skill 如果保留是否会改善结果。

### 10.4.1 类 CPI 综合指标：ACPS

只报告 pass rate 不够，因为两个系统可能通过率相同，但一个系统 1 轮就能通过，另一个系统需要 5 轮反复修复。为了量化这种差异，建议引入一个类似 CPI 的指标：

> ACPS，即 Average Cost Per Solved task，表示每解决一个任务平均需要多少 agent 成本。

最简单版本可以只用迭代次数：

```text
ACPS_iter = total_agent_iterations / solved_tasks
```

其中一次 `coder -> evaluator` 闭环记为一个 agent iteration。如果一个任务第 1 次生成就通过，则成本为 1；如果经过 3 次修复后通过，则成本为 4。

但为了避免失败任务被忽略，推荐使用带失败惩罚的版本：

```text
ACPS_iter_penalty =
  (sum(iterations_of_solved_tasks) + penalty * failed_tasks)
  / solved_tasks
```

其中 `penalty` 可以设为 `K + 1`，`K` 是最大允许修复轮数。例如最多允许 5 次尝试，则失败任务按 6 次迭代计入成本。这样，一个系统不能通过只解决少数简单任务来获得虚假的低 ACPS。

进一步，可以定义综合成本版本：

```text
cost(task) =
  w_iter  * iterations
  + w_tok * normalized_tokens
  + w_tool * tool_calls
  + w_time * normalized_wall_time

ACPS_cost =
  (sum(cost_of_solved_tasks) + penalty_cost * failed_tasks)
  / solved_tasks
```

论文实验中建议同时报告三个数：

- Pass@K：能解决多少任务。
- ACPS_iter：解决任务平均需要多少轮。
- ACPS_cost：综合考虑迭代、token、工具调用和时间后的平均成本。
- AST：单位 agent 迭代/成本带来的 solved task 数量，便于和 pass rate 一起展示整体吞吐。

这样可以区分三类系统：

- 高 Pass@K、低 ACPS：理想系统，既能解又高效。
- 高 Pass@K、高 ACPS：能解，但依赖大量修复和上下文成本。
- 低 Pass@K、低 ACPS：看似成本低，但实际只解决了少量简单任务。

为了让不同实验可比，所有 ACPS 指标都应在相同最大迭代次数 `K`、相同工具集合、相同 skill token budget 下计算。

ACPS 是越低越好，AST 是越高越好。二者可以互为补充：

```text
AST_iter = solved_tasks / total_agent_iterations
```

如果 `solved_tasks = 0`，则 ACPS 记为无穷大，AST 记为 0。

### 10.5 Ablation

做以下消融实验：

- 去掉 recency。
- 去掉 topic locality。
- 去掉 failure-signature locality。
- 去掉 graph expansion。
- 去掉 utility statistics。
- 去掉 skill validation gate。
- 改变 skill 上下文预算：2k、4k、8k、16k tokens。

### 10.6 统计检验

建议使用成对任务比较：

- 对 pass/fail 使用 McNemar test。
- 对 pass-rate delta 使用 bootstrap confidence interval。
- 对 token/iteration 差异使用 Wilcoxon signed-rank test。
- 报告 effect size，不只报告 p-value。

### 10.7 可以写进论文的主张

比较强的论文结论可以写成：

> 在固定 8k skill context budget 下，locality-aware skill cache 相比 semantic top-k retrieval 将 Pass@5 提升 X 个百分点，将每个 solved task 的 token 消耗降低 Y%，并在自动 skill 演化过程中保持更低的 regression rate。

避免空泛地说“agent 学会了”。更准确的说法是：

- Agent 积累了外部过程性记忆。
- Agent 能检索并应用经过验证的 skill。
- Agent 在可测 benchmark 上随时间提升任务表现。

## 11. 最小仓库结构

```text
selfimprovecoderandevaluator/
  agents/
    coder.py
    evaluator.py
    prompts/
      coder_core.md
      evaluator_core.md
  cache/
    fingerprint.py
    retrieve.py
    policy.py
    pack.py
  skills/
    seed/
      rtl_rules.yaml
      evaluator_rules.yaml
    active/
    candidate/
    rejected/
  harness/
    task_schema.py
    run_task.py
    tools.py
    score.py
  benchmarks/
    tasks/
  experiments/
    run_experiment.py
    configs/
  results/
  docs/
```

## 12. 第一版原型里程碑

第一版有价值的 prototype 不需要很大，建议只做：

1. 加载 20-50 个 HDL 任务。
2. Coder/evaluator loop 最多修复 3 轮。
3. 准备 30-80 个规范化 seed skills。
4. 比较 fixed prompt、semantic top-k、本文 cache policy。
5. 输出 pass rate、token、iteration、retrieved skills 的结果表。

这足以判断缓存想法是否有实验信号，再决定是否投入更完整的自动演化系统。

## 13. 风险与控制

风险：Evaluator 生成的测试太弱，导致 false pass。

控制：使用 hidden tests、formal properties 和 benchmark 自带 oracle。

风险：Skill 演化变成 prompt 膨胀。

控制：要求每个 skill 有触发条件、反触发条件、证据和 A/B 验证。

风险：检索到看似相关但实际有害的 skill。

控制：记录 negative examples 和 `conflicts_with` 边。

风险：提升来自更长 prompt，而不是更好的 cache policy。

控制：所有 retrieval 方法使用相同 skill token budget。

风险：benchmark leakage。

控制：按任务来源和任务族划分 evolution、validation、test sets。

## 14. 推荐初始 Seed Skills

建议先准备紧凑、高收益的 seed skills：

- 严格保持接口不变。
- 时钟/reset 语义识别。
- 阻塞/非阻塞赋值规则。
- 组合逻辑默认赋值。
- 避免 inferred latch。
- signed/unsigned 算术。
- 位宽扩展和截断。
- FSM state/next-state 分离。
- 单周期 pulse 生成。
- 边沿检测。
- 带终止条件的 counter。
- valid/ready handshake 稳定性。
- FIFO full/empty pointer 逻辑。
- round-robin arbiter fairness。
- testbench clock/reset 骨架。
- directed edge-case tests。
- randomized scoreboard tests。
- Verilator warning 解释。
- Icarus compile/run flow。
- SymbiYosys property 骨架。

## 15. 关键设计判断

这个系统不应该把“prompt”当作核心资产，而应该把“经过验证、类型化、可度量的过程性知识”当作核心资产。

Prompt engineering 是表层；context engineering 才是这个项目的核心。它包括：

- memory hierarchy；
- retrieval policy；
- cache admission；
- cache replacement；
- skill compression；
- skill validation；
- 以及证明“正确知识在正确时间进入有限上下文”的实验方法。

如果论文要有清晰贡献，可以把贡献总结为三点：

1. 提出面向 HDL agent 的规范化 skill memory 表示。
2. 提出基于时间局部性和问题局部性的 skill cache 策略。
3. 通过受控实验说明该策略优于固定 prompt 和朴素语义检索。
