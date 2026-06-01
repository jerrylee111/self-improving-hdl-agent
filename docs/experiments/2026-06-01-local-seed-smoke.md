# 2026-06-01 Local Seed Smoke Experiment

## 目的

这次实验是项目的第一轮端到端实验，目标不是证明 skill cache 已经有效，而是确认以下链路可以稳定工作：

1. 读取标准化 HDL task YAML。
2. 检索 seed skills。
3. 调用 DeepSeek 生成 RTL。
4. 自动生成 testbench。
5. 运行 `verilator + iverilog + vvp`。
6. 记录实验结果，计算 Pass@K、ACPS、AST。

## 配置

- Config: `experiments/configs/smoke.yaml`
- Dataset: `benchmarks/tasks/local_seed/*.yaml`
- Tasks: 12
- Policy: `fixed`
- Max repair iterations: 3
- Model: local `.env` 中配置的 DeepSeek model
- Run directory: `results/experiments/smoke_20260601_105628`

## 汇总结果

```json
{
  "tasks": 12,
  "solved": 12,
  "failed": 0,
  "pass_at_k": 1.0,
  "total_iterations": 12,
  "acps_iter": 1.0,
  "ast_iter": 1.0
}
```

额外 wall-time 统计：

- Total wall time: 274.912 s
- Mean wall time: 22.909 s/task
- Median wall time: 10.021 s/task
- Max wall time: 71.662 s

## 逐任务结果

| Task | Family | Passed | Iterations | Wall Time |
| --- | --- | --- | ---: | ---: |
| local_arith_full_adder | arithmetic_basic | true | 1 | 3.776 s |
| local_arith_half_adder | arithmetic_basic | true | 1 | 4.064 s |
| local_comb_and_gate | combinational_basic | true | 1 | 3.249 s |
| local_comb_mux2 | combinational_mux | true | 1 | 4.161 s |
| local_counter_mod10 | sequential_counter | true | 1 | 9.474 s |
| local_dff_sync_reset | sequential_register | true | 1 | 4.314 s |
| local_edge_detect_rise | sequential_edge_detect | true | 1 | 60.428 s |
| local_fsm_101_detector | sequential_fsm | true | 1 | 59.310 s |
| local_popcount4 | arithmetic_basic | true | 1 | 32.166 s |
| local_priority_encoder4 | combinational_encoder | true | 1 | 11.740 s |
| local_valid_ready_skid | handshake_basic | true | 1 | 71.662 s |
| local_vector_reverse8 | vector_ops | true | 1 | 10.568 s |

## 观察

1. 第一版 coder/evaluator/harness 管线已经可以跑真实 LLM 生成和本地 HDL 验证。
2. 12 个 local seed tasks 全部 Pass@1，说明基础任务集目前偏简单。
3. `valid_ready_skid`、`edge_detect`、`fsm_101_detector` 的 wall time 明显较高，后续需要记录 LLM latency/token usage，并增加 timeout/retry。
4. 当前 `fixed` policy 每次取 6 个 skill，任务少时足够，但无法证明 cache policy 优于其他策略。

## 结论

这次实验可以作为系统 smoke baseline：

- Pass@3 = 100%
- ACPS_iter = 1.0
- AST_iter = 1.0

但它不能作为 skill cache 有效性的证据。下一步必须加入对照组和更难数据集。

## 下一步

建议立刻做三件事：

1. 增加 baseline policy：
   - `no_skill`
   - `fixed`
   - `semantic_or_tag_topk`
   - `locality_aware`
2. 扩展数据：
   - 接入 VerilogEval 子集。
   - 增加更难的 local tasks，例如 FIFO、arbiter、multi-cycle handshake。
3. 增强指标：
   - 记录 prompt/completion tokens。
   - 记录 LLM latency。
   - 增加 `ACPS_cost`，把 iteration、token、tool calls、wall time 合并。
