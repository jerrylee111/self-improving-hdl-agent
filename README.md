# Self-Improving HDL Coder/Evaluator

This is an early research prototype for a Verilog/SystemVerilog coding agent.

The basic idea is simple: instead of trying to fine-tune a closed model, we let an agent build up an external library of HDL skills, then retrieve only the useful pieces into context for each task. The project is currently focused on two agents:

- `coder`: writes or repairs RTL.
- `evaluator`: generates/runs checks and gives feedback.

The part I care about most is the skill cache. Skills live outside the model context, and the system should pull them in using signals like task similarity, recent usefulness, failure type, token cost, and cache-style replacement policies. The long-term goal is to make this measurable, not just a nice story.

## Current State

This repo already has a small working loop:

1. Load a normalized HDL task YAML.
2. Retrieve seed RTL skills.
3. Call a DeepSeek-compatible OpenAI API client.
4. Generate RTL.
5. Generate a local testbench.
6. Run `verilator`, `iverilog`, and `vvp`.
7. Retry for a few repair iterations if needed.
8. Write a `result.json` for later metrics.

It is not a polished benchmark system yet. It is a scaffold that can run real demos and is meant to grow into a controlled experiment framework.

## Quick Start

Install dependencies:

```bash
uv sync
```

Create a local environment file:

```bash
cp .env.example .env
```

Fill in your API key:

```bash
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
```

Check the local HDL toolchain:

```bash
uv run sic-run-task benchmarks/tasks/local_seed/comb_and_gate.yaml --policy fixed --dry-run
```

Run a real demo:

```bash
uv run sic-run-task benchmarks/tasks/local_seed/comb_and_gate.yaml --policy fixed --no-dry-run --max-iters 3
```

Try a sequential task:

```bash
uv run sic-run-task benchmarks/tasks/local_seed/counter_mod10.yaml --policy fixed --no-dry-run --max-iters 3
```

Results are written under:

```text
results/runs/<task_id>/
```

## Toolchain

The first prototype uses:

- `verilator` for lint.
- `iverilog` for compile.
- `vvp` for simulation.
- DeepSeek through the OpenAI-compatible API.

`yosys` and SymbiYosys are planned for the formal verification layer, but they are not required for the first demo.

## Dataset Plan

The dataset work is split into tiers:

- Local seed tasks for development and regression.
- VerilogEval-style tasks for the main functional correctness benchmark.
- RTLLM-style design tasks for out-of-family generalization.
- Synthetic mutation tasks for evaluator and skill-evolution diagnostics.

The local seed set is already in `benchmarks/tasks/local_seed/`.

## Research Metrics

The system is designed to report more than pass rate. The current plan includes:

- `Pass@K`: how many tasks are solved within K attempts.
- `ACPS`: average cost per solved task, similar in spirit to CPI.
- `AST`: agent solution throughput, the inverse view of ACPS.
- Cache hit/useful-hit rates.
- Skill pollution and eviction regret.

The point is to show whether a skill cache actually helps under a fixed context budget.

## Docs

- [Research plan](docs/skill_cache_agent_research_plan.md)
- [System environment setup](docs/system_environment_setup.md)
- [Dataset landing plan](docs/dataset_landing_plan.md)

## License

MIT License.
