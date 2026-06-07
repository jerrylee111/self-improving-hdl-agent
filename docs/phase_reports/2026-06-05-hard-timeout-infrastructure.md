# 阶段报告：硬超时与基础设施失败隔离

日期：2026-06-05

## 背景

`verilogeval_seq20_cache_ablation` 正式试跑暴露出一个关键问题：当前 timeout 是协作式的，只能在 attempt 边界检查，无法打断正在等待的单次 LLM 请求。结果中出现过 1000s 以上的 wall time，导致能力指标被 API timeout/connection error 严重污染。

因此本阶段优先修复实验基础设施，而不是继续扩大实验规模。

## 本阶段实现

### 1. 拆分 task loop core

`harness/runner.py`

新增：

`run_task_loop_with_context`

父进程先完成 L1 cache lookup，得到：

- `skills`
- `cache_event`

然后子进程只负责执行 coder/evaluator loop。这样可以在保留父进程 L1 状态的同时，对每个 task run 做硬超时。

### 2. Worker 子进程

新增：

`experiments/run_task_worker.py`

输入：

- task path
- policy
- max iters
- L1 skills
- cache event
- evaluator profile

输出：

- 单个 task record JSON

### 3. Task-set runner 支持 hard timeout

`experiments/run_taskset_ablation.py`

新增配置项：

`hard_timeout: true`

当启用后，父进程使用：

```text
subprocess.run(..., timeout=max_task_wall_time_s)
```

超过 wall-time 会直接终止 worker 子进程，并生成一条 infrastructure failure record。

### 4. Summary 指标更新

`harness/runner.py`

summary 新增：

- `infrastructure_failures`

同时 `hdl_failed` 不再包含 API failure 和 infrastructure failure。

## 验证

### 正常 worker smoke

配置：

`experiments/configs/verilogeval_hard_timeout_smoke.yaml`

结果目录：

`results/taskset_ablation/verilogeval_hard_timeout_smoke_20260605_165223/`

结果：

| condition | solved | pass@k | ACPS-Iter | timeouts |
| --- | ---: | ---: | ---: | ---: |
| `ht_no_skill` | 2/2 | 1.0 | 1.0 | 0 |
| `ht_seed_only` | 1/2 | 0.5 | 2.0 | 0 |

说明 worker 子进程路径可以正常返回有效 iterations 和 evaluator 结果。

### 强制 timeout smoke

临时配置：

`max_task_wall_time_s: 1`

结果目录：

`results/taskset_ablation/verilogeval_hard_timeout_smoke_20260605_165341/`

结果：

| condition | solved | timeouts |
| --- | ---: | ---: |
| `ht_no_skill` | 0/1 | 1 |

说明父进程可以强制 kill 超时 worker，并把它记录为 timeout/infrastructure failure。

## 重要说明

硬超时修复后，后续 seq20 重跑的 wall time 会更可信。超时任务会被截断，不会再拖到数百或上千秒。

但 hard timeout 也带来一个实验语义变化：超时任务不再产生 repair feedback 和 candidate skill。这是合理的，因为它属于 infrastructure failure，不应被当成 HDL failure 进入 skill mining。

## 下一步

1. 用 hard timeout 重跑 `verilogeval_seq5_cache_ablation.yaml`，确认新 runner 与旧结果趋势是否一致。
2. 用 hard timeout 重跑 `verilogeval_seq20_cache_ablation.yaml`。
3. 在报告中同时给出：
   - raw pass@k
   - effective pass@k
   - infrastructure failure rate
   - timeout rate
4. 继续做 candidate block validation，避免未验证 skill 污染 active store。
