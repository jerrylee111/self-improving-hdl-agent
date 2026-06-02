# 2026-06-02 Local Hard Task Notes

## 目的

这次尝试是在 local seed 之外补充更难的本地任务，目标是让实验不再被简单组合/基础时序任务“全部 Pass@1”淹没。

新增 hard tasks：

- `local_fifo_sync_depth4`
- `local_round_robin_arbiter2`
- `local_valid_ready_pipeline2`
- `local_mul4_shift_add`

## 有效样本

来自 `results/experiments/local_hard_ablation_20260601_152512/records.jsonl` 的有效 HDL 样本：

| Policy | Task | Passed | Iterations | Notes |
| --- | --- | --- | ---: | --- |
| no_skill | local_fifo_sync_depth4 | true | 1 | FIFO 通过 |
| no_skill | local_round_robin_arbiter2 | false | 3 | 真实 HDL 失败 |
| no_skill | local_valid_ready_pipeline2 | true | 1 | Pipeline 通过 |
| no_skill | local_mul4_shift_add | true | 1 | Multiplier 通过 |
| tag_topk | local_fifo_sync_depth4 | true | 1 | FIFO 通过 |
| tag_topk | local_round_robin_arbiter2 | true | 2 | 第二轮修复后通过 |

补跑时出现的失败多为 API timeout：

- `APITimeoutError: Request timed out.`
- `APIConnectionError: Connection error.`

这些样本不应该计入 HDL correctness 对比。

## 关键样例：Round-Robin Arbiter

`local_round_robin_arbiter2` 是目前最有价值的 hard 样例。

### no_skill

`no_skill` 生成了组合 grant，并用状态位决定当前优先级：

```verilog
assign grant[0] = req[0] && (!req[1] || (req[1] && priority_reg == 1'b0));
assign grant[1] = req[1] && (!req[0] || (req[0] && priority_reg == 1'b1));
```

问题是 testbench 在 `posedge clk` 后采样 `grant`。当 `req == 2'b11` 时，状态位在同一个时钟边沿翻转，采样时看到的是下一优先级对应的组合 grant，而不是当前 granted cycle 的 grant。因此 3 轮修复仍失败：

```text
FATAL: tb.sv:9: grant mismatch
```

### tag_topk

`tag_topk` 第二轮生成了 registered grant：

```verilog
always @(posedge clk) begin
    if (reset) begin
        prio <= 1'b0;
        grant <= 2'b00;
    end else begin
        prio <= next_prio;
        grant <= next_grant;
    end
end
```

这与 testbench 的采样语义匹配，因此通过。

## 初步结论

1. Hard tasks 已经能制造真实失败，不再是全部 Pass@1。
2. `local_round_robin_arbiter2` 显示出 skill/context 可能改变实现风格，并影响修复结果。
3. 当前 API 稳定性会干扰实验，需要把 API timeout/connection error 与 HDL failure 分开统计。
4. `summary_records` 已补充 `api_failures` 和 `hdl_failed` 字段，避免把 API 问题误算为模型/skill 失败。

## 下一步

1. 增加 arbiter 相关 seed skill：
   - registered grant vs combinational grant 的时序语义。
   - round-robin priority pointer 更新时机。
2. 给 LLM call 记录 per-call latency 和 timeout 状态。
3. 重跑 hard ablation，但过滤 API failure。
4. 接入 VerilogEval 前，先把 local hard tasks 扩展到 10-20 个。
