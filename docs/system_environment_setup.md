# 系统基础环境搭建方案

## 1. 当前机器环境检查

当前工作区：

```text
/Users/liruijie/Desktop/selfimprovecoderandevaluator
```

已经确认可用：

- macOS arm64。
- `uv` 已安装。
- `verilator` 已安装：可用于 SystemVerilog lint 和部分仿真。
- `iverilog` 已安装：可用于 Verilog 编译和仿真。
- `pipx` 已安装。

暂未发现：

- `yosys`。
- `sby`，即 SymbiYosys。

结论：

- 第一阶段可以先用 `verilator + iverilog` 搭建动态验证闭环。
- 第二阶段再补 `yosys + sby` 做形式验证。

## 2. Agent 框架选择

我们需要的不是一个完整黑盒 coding assistant，而是一个可以深度修改 memory、skill、cache、retrieval、evaluation loop 的研究型 agent 系统。

候选方案：

| 方案 | 优点 | 问题 | 结论 |
| --- | --- | --- | --- |
| OpenHands | 完整开源 coding agent，已有文件/终端/浏览器操作能力，适合作为 coding-agent 参考实现 | 系统较重，面向通用软件开发；要把 skill cache 和 HDL evaluator 深度嵌进去，改造成本较高 | 作为参考，不作为第一版核心 |
| AutoGen | 多 agent 对话成熟，适合 coder/evaluator 形式 | 当前生态正在向 Microsoft Agent Framework 迁移，长期接口稳定性需要观察 | 可参考通信模式 |
| CrewAI | 角色式多 agent 易上手 | 更偏任务编排，不适合精细控制 cache replacement 和实验指标 | 不作为核心 |
| LangGraph | 图式状态机清晰，适合显式控制 coder/evaluator/retriever/evolver 节点 | 需要自己写具体工具和 skill store | 推荐作为编排层 |
| 自研轻量 loop | 最可控，最适合论文实验和 ablation | 需要自己补 observability、重试、状态管理 | 推荐第一版采用 |

推荐决策：

> 第一版不要直接 fork 一个庞大的 coding agent，而是采用“轻量自研 agent loop + 可选 LangGraph 编排”的路线。

原因：

1. 我们的研究核心是 skill cache，不是通用 coding agent UI。
2. Coder/evaluator 的状态转移非常清晰，用小型状态机即可表达。
3. 自研 loop 最容易做消融实验，比如替换 `semantic top-k`、`LRU`、`LFU`、`locality-aware cache`。
4. 后续如果需要更强工具能力，可以借鉴 OpenHands 的 tool abstraction，而不是一开始被大型框架牵着走。

## 3. DeepSeek API 接入方式

DeepSeek 官方 API 支持 OpenAI-compatible 调用格式。建议使用 OpenAI Python SDK，通过 `base_url` 指向 DeepSeek。

环境变量：

```bash
export DEEPSEEK_API_KEY="你的 key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-v4-pro"
```

代码侧统一封装成 `LLMClient`，避免业务代码直接依赖 DeepSeek。这样以后切换 Claude、Gemini、OpenAI 或本地模型时，只需要替换 client。

如果要优先控制成本，可以把 `DEEPSEEK_MODEL` 改成 `deepseek-v4-flash`。不要把第一版默认值设成 `deepseek-chat`，因为 DeepSeek 官方文档显示该兼容别名将在 2026-07-24 废弃。

## 4. 推荐 Python 环境

虽然当前系统 Python 是 3.14，但建议项目使用 Python 3.12 或 3.13：

- 很多 agent framework、向量库、仿真工具 wrapper 对 3.12 支持更稳。
- 3.14 太新，依赖兼容性风险更高。

推荐命令：

```bash
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv sync
```

## 5. Python 依赖分层

第一阶段核心依赖：

- `openai`：用于调用 DeepSeek OpenAI-compatible API。
- `pydantic`：定义 task、skill、agent message、experiment record。
- `pyyaml`：读写 skill YAML。
- `typer`：命令行入口。
- `rich`：漂亮日志和实验表格。
- `jinja2`：生成 prompt、testbench、工具脚本。
- `numpy`：统计和打分。

第二阶段检索依赖：

- `sentence-transformers` 或外部 embedding API。
- `chromadb` 或 `lancedb`。
- `scikit-learn`：baseline 检索、相似度和简单 ablation。

第三阶段实验分析：

- `pandas`。
- `scipy`。
- `matplotlib`。

## 6. HDL 工具链

第一阶段已可用：

```bash
verilator --version
iverilog -V
```

建议补充：

```bash
brew install yosys
```

SymbiYosys 的安装方式容易随发行渠道变化，建议第二阶段单独处理。第一版先不要卡在 formal 工具上。

第一阶段工具职责：

- `verilator --lint-only -Wall design.sv`：快速发现语法、位宽、锁存器等问题。
- `iverilog -g2012 -o sim.out tb.sv design.sv`：编译仿真。
- `vvp sim.out`：运行仿真。

第二阶段工具职责：

- `yosys`：综合检查、简单形式转换。
- `sby`：property/formal verification。

## 7. 初始仓库结构

建议结构：

```text
selfimprovecoderandevaluator/
  agents/
    coder.py
    evaluator.py
    loop.py
    llm.py
    messages.py
  cache/
    fingerprint.py
    retrieve.py
    policy.py
    pack.py
  skills/
    seed/
    active/
    candidate/
    rejected/
  harness/
    task_schema.py
    tools.py
    run_task.py
    score.py
  experiments/
    run_experiment.py
    configs/
  benchmarks/
    tasks/
  results/
  docs/
```

## 8. 第一阶段最小闭环

第一阶段目标不是追求系统完整，而是把研究闭环跑起来：

1. 读入一个 HDL task YAML。
2. 通过 task fingerprint 找到少量 seed skills。
3. 调用 DeepSeek 生成 RTL。
4. Evaluator 生成 testbench 或使用任务自带 testbench。
5. 运行 `verilator` 和 `iverilog`。
6. 如果失败，把日志结构化后交给 coder 修复。
7. 最多修复 `K` 轮。
8. 记录 Pass@K、ACPS、AST、token、工具调用次数、skill 使用情况。

## 9. 为什么不直接改 OpenHands

OpenHands 是很好的参考对象，因为它是通用 coding agent，具备 shell、文件系统、浏览器等能力。但当前项目不建议第一版直接 fork 它：

- 我们的任务域很窄：HDL 代码生成和验证。
- 我们需要对 skill cache 做精确实验控制。
- 大型 agent 框架会引入很多与论文变量无关的因素。
- 消融实验需要能快速替换 policy，而不是在复杂框架里绕开默认行为。

更合适的做法：

> 第一版自研轻量 loop；第二版吸收 OpenHands 的 sandbox/tool abstraction；第三版再考虑把我们的 skill cache 封装成插件或 SDK。

## 10. 环境搭建命令草案

```bash
cd /Users/liruijie/Desktop/selfimprovecoderandevaluator

uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv sync

cp .env.example .env
# 然后在 .env 中填入 DEEPSEEK_API_KEY

verilator --version
iverilog -V
```

## 10.1 运行第一条真实任务

创建本地 `.env`：

```bash
cp .env.example .env
```

然后在 `.env` 中填入：

```bash
DEEPSEEK_API_KEY=你的 DeepSeek API key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
```

先做 dry-run，检查任务、schema 和 HDL 工具链：

```bash
uv run sic-run-task benchmarks/tasks/local_seed/comb_and_gate.yaml --policy fixed --dry-run
```

调用 DeepSeek 并运行本地 evaluator：

```bash
uv run sic-run-task benchmarks/tasks/local_seed/comb_and_gate.yaml --policy fixed --no-dry-run --max-iters 3
```

运行结束后，产物会写入：

```text
results/runs/<task_id>/
  attempt_1/design.v
  attempt_1/tb.sv
  attempt_1/sim.out
  result.json
```

`result.json` 中会记录：

- task id；
- policy；
- retrieved skills；
- pass/fail；
- iterations；
- wall time；
- workdir。

这些字段后续可直接用于计算 Pass@K、ACPS 和 AST。

如果后续需要形式验证：

```bash
brew install yosys
```

## 11. 第一版成功标准

环境搭建完成后，第一版系统应该能做到：

- `python -m harness.run_task benchmarks/tasks/example.yaml --policy fixed`
- `python -m experiments.run_experiment experiments/configs/smoke.yaml`
- 生成 `results/*.jsonl`。
- 每条实验记录包含：
  - task id；
  - policy；
  - retrieved skills；
  - pass/fail；
  - iterations；
  - token usage；
  - tool calls；
  - ACPS/AST 所需字段。

这样就能开始真正验证“skill cache 是否有用”。

## 12. 资料来源

- [DeepSeek API Docs](https://api-docs.deepseek.com/)：官方文档说明 DeepSeek API 兼容 OpenAI/Anthropic 格式，OpenAI-compatible base URL 为 `https://api.deepseek.com`，并列出 `deepseek-v4-pro` 和 `deepseek-v4-flash`。
- [DeepSeek Change Log](https://api-docs.deepseek.com/updates/)：官方变更日志显示 `deepseek-chat` 和 `deepseek-reasoner` 将在 2026-07-24 废弃。
- [LangGraph GitHub](https://github.com/langchain-ai/langgraph)：MIT 许可的低层级 stateful agent orchestration framework，适合作为第二阶段可选编排层。
- [OpenHands GitHub](https://github.com/OpenHands/OpenHands)：MIT 许可的开源 coding agent 平台，适合作为通用 coding-agent 参考。
- [AutoGen Docs](https://microsoft.github.io/autogen/dev/index.html)：Microsoft 的多 agent 框架，适合参考 agent 通信和 runtime 设计。
- [CrewAI GitHub](https://github.com/crewAIInc/crewAI)：MIT 许可的多 agent orchestration framework，适合参考角色式 agent 协作。
