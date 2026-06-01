# 2026-06-01 Local Policy Ablation Small

## 目的

这次实验在第一轮 smoke experiment 的基础上补充 policy 对照组，目标是检查：

1. 无 skill 时，DeepSeek 在 local seed 子集上是否已经足够强。
2. 固定塞入全部 seed skills 是否会带来收益或噪声。
3. 简单任务相关检索 `tag_topk` 是否比固定 prompt 更稳定。
4. 轻量 `locality_aware` 策略是否具备进一步发展的实验价值。

## 配置

- Config: `experiments/configs/local_policy_ablation_small.yaml`
- Tasks: 6
- Policies:
  - `no_skill`
  - `fixed`
  - `tag_topk`
  - `locality_aware`
- Max repair iterations: 3
- Total task-policy runs: 24
- Run directory: `results/experiments/local_policy_ablation_small_20260601_110917`

任务子集：

- `local_comb_and_gate`
- `local_popcount4`
- `local_priority_encoder4`
- `local_counter_mod10`
- `local_fsm_101_detector`
- `local_valid_ready_skid`

## 汇总结果

| Policy | Solved | Pass@3 | Iterations | ACPS_iter | AST_iter | Wall Total | Wall Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no_skill | 6/6 | 1.000 | 6 | 1.000 | 1.000 | 281.081s | 46.847s |
| fixed | 6/6 | 1.000 | 8 | 1.333 | 0.750 | 506.390s | 84.398s |
| tag_topk | 6/6 | 1.000 | 6 | 1.000 | 1.000 | 224.003s | 37.334s |
| locality_aware | 6/6 | 1.000 | 6 | 1.000 | 1.000 | 271.115s | 45.186s |

整体 summary：

```json
{
  "tasks": 24,
  "solved": 24,
  "failed": 0,
  "pass_at_k": 1.0,
  "total_iterations": 26,
  "acps_iter": 1.0833,
  "ast_iter": 0.9231
}
```

## 关键观察

1. 所有 policy 都达到 Pass@3 = 100%，说明 local seed 子集仍然偏简单。
2. `fixed` policy 的 ACPS_iter = 1.333，比其他 policy 差，因为它在两个任务上需要第二轮修复。
3. `tag_topk` 达到最低 wall total，并且保持 ACPS_iter = 1.0。
4. `no_skill` 也能全部 Pass@1，说明当前任务还不能证明 skill cache 对 pass rate 的提升。
5. 这次实验已经能说明一个负面结论：固定塞入更多 skill 不一定更好，skill selection/admission 是必要的。

## Fixed Policy 的两个失败点

### `local_fsm_101_detector`

`fixed` 第一轮生成的 FSM 使用组合输出：

```verilog
assign found = (state == S10) & bit_in;
```

在当前 testbench 中，`found` 需要在时钟边沿后按已采样历史判断。第一轮实现的输出时序不匹配，因此触发：

```text
FATAL: tb.sv:12: fsm mismatch
```

第二轮根据 evaluator feedback 修复后通过。

### `local_valid_ready_skid`

`fixed` 第一轮在 SystemVerilog 中对默认 wire 类型的 output `in_ready` 做过程赋值：

```text
%Error-PROCASSWIRE: Procedural assignment to wire ... 'in_ready'
```

这是一个很典型的 SystemVerilog 端口类型问题。第二轮修复后通过。

## 结论

这次 ablation 还不能证明 locality-aware cache 在通过率上优于其他方法，但已经证明：

- 只看 Pass@K 不够，必须看 ACPS/AST。
- 固定 prompt/固定 skill dump 可能引入噪声。
- 任务相关的 top-k skill selection 比固定塞满更稳。
- 下一步应该用更难 benchmark 拉开 pass rate 差异。

## 下一步

1. 加入更难任务：
   - FIFO。
   - round-robin arbiter。
   - valid/ready pipeline。
   - multi-cycle arithmetic。
   - 更复杂 FSM。
2. 接入 VerilogEval 子集。
3. 增加 LLM 观测字段：
   - prompt tokens。
   - completion tokens。
   - per-call latency。
   - retry/timeout 状态。
4. 把 `locality_aware` 从静态排序升级为真正的 cache policy：
   - usage history。
   - success/failure EMA。
   - token cost。
   - redundancy penalty。
   - eviction/admission decision。
