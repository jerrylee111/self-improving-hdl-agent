# FSMSeq Locality Probe 实验

日期：2026-06-15

## 背景

`short-stress4` 三轮实验中，`Prob096 fsmseq` 是最重要的 L1 hit utility 样本：

- seed-only/active 有时 hit 后通过；
- active 第三轮出现 hit 后 timeout；
- 同一个任务族的 hit 既可能正收益，也可能负收益。

因此本轮拆成两个更小的 probe：

1. `targeted_fsmseq`：只跑 `fsmseq`，观察冷启动单任务是否能命中；
2. `warmed_fsmseq`：先跑 `fsm2s` 作为 warmup，再跑 `fsmseq`，观察时间局部性是否触发 L1 hit。

## 配置

冷启动单任务配置：

```text
experiments/configs/verilogeval_targeted_fsmseq.yaml
```

warmed sequence 配置：

```text
experiments/configs/verilogeval_warmed_fsmseq.yaml
```

两个配置都使用：

- `max_repair_iters: 2`
- `skill_l1_capacity: 6`
- `hard_timeout: true`
- `max_task_wall_time_s: 180`
- `evaluator_profile: adversarial_v2`

## Targeted FSMSeq：冷启动单任务

运行三轮：

```bash
uv run python experiments/run_taskset_ablation.py \
  experiments/configs/verilogeval_targeted_fsmseq.yaml \
  --no-dry-run
```

输出目录：

```text
results/taskset_ablation/verilogeval_targeted_fsmseq_20260615_171133/
results/taskset_ablation/verilogeval_targeted_fsmseq_20260615_171602/
results/taskset_ablation/verilogeval_targeted_fsmseq_20260615_172127/
```

三轮汇总：

| condition | pass@k runs | mean pass@k | ACPS runs | mean ACPS | L1 hit runs | timeouts |
| --- | --- | ---: | --- | ---: | --- | --- |
| no-skill | 1.0, 1.0, 1.0 | 1.0 | 1.0, 2.0, 2.0 | 1.6667 | 0, 0, 0 | 0, 0, 0 |
| seed-only | 1.0, 1.0, 1.0 | 1.0 | 2.0, 2.0, 2.0 | 2.0 | 0, 0, 0 | 0, 0, 0 |
| active | 1.0, 1.0, 1.0 | 1.0 | 2.0, 2.0, 1.0 | 1.6667 | 0, 0, 0 | 0, 0, 0 |

逐轮观察：

| run | condition | result | iterations | L1 event | wall time |
| --- | --- | --- | ---: | --- | ---: |
| 1 | no-skill | pass | 1 | miss | 61.381s |
| 1 | seed-only | pass | 2 | miss | 105.274s |
| 1 | active | pass | 2 | miss | 90.086s |
| 2 | no-skill | pass | 2 | miss | 79.739s |
| 2 | seed-only | pass | 2 | miss | 103.334s |
| 2 | active | pass | 2 | miss | 119.751s |
| 3 | no-skill | pass | 2 | miss | 59.861s |
| 3 | seed-only | pass | 2 | miss | 118.111s |
| 3 | active | pass | 1 | miss | 43.596s |

### Targeted 结论

冷启动单任务没有复现 `short-stress4` 中的 L1 hit：

```text
seed-only: 0/3 hit
active:    0/3 hit
```

这说明当前 L1 hit 不只是由任务语义决定，还依赖任务序列中的时间局部性。换句话说，单独拿 `fsmseq` 出来跑，会改变 cache 状态，不能直接复现多任务序列里的 hit 行为。

## Warmed FSMSeq：时间局部性 probe

warmed 配置包含两个任务：

1. `Prob111 fsm2s`：FSM warmup；
2. `Prob096 fsmseq`：FSM probe。

运行一轮：

```bash
uv run python experiments/run_taskset_ablation.py \
  experiments/configs/verilogeval_warmed_fsmseq.yaml \
  --no-dry-run
```

输出目录：

```text
results/taskset_ablation/verilogeval_warmed_fsmseq_20260615_172607/
```

汇总结果：

| condition | solved | pass@k | ACPS-Iter | L1 hit | candidates | timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| no-skill | 1/2 | 0.5 | 4.0 | 0/2 | 4 | 0 |
| seed-only | 2/2 | 1.0 | 2.0 | 1/2 | 4 | 0 |
| active | 2/2 | 1.0 | 1.5 | 1/2 | 2 | 0 |

逐任务结果：

| condition | task | result | iterations | L1 event | loaded skills | wall time |
| --- | --- | --- | ---: | --- | --- | ---: |
| no-skill | fsm2s | pass | 2 | miss | none | 24.272s |
| no-skill | fsmseq | fail | 2 | miss | none | 58.821s |
| seed-only | fsm2s | pass | 2 | miss | seq_nonblocking, fsm_overlap, interface_exact | 28.907s |
| seed-only | fsmseq | pass | 2 | hit | seq_nonblocking, fsm_overlap, interface_exact | 71.194s |
| active | fsm2s | pass | 2 | miss | seq_nonblocking, fsm_overlap, interface_exact | 23.892s |
| active | fsmseq | pass | 1 | hit | seq_nonblocking, fsm_overlap, interface_exact | 37.294s |

### Warmed 结论

warmed sequence 成功复现了时间局部性：

```text
targeted_fsmseq: seed/active 的 fsmseq 全部 miss
warmed_fsmseq:   seed/active 的 fsmseq 都 hit
```

并且在这一轮中，hit 后产生了正收益：

- no-skill 的 `fsmseq` 失败；
- seed-only 的 `fsmseq` hit 后通过；
- active 的 `fsmseq` hit 后 1 次迭代通过，ACPS 优于 seed-only。

## 对缓存假设的意义

这轮实验给出了一个比 pass@k 更重要的证据：

```text
L1 skill cache 的行为确实具有时间局部性。
```

同一个 `fsmseq` 任务：

- 冷启动单独运行时，seed/active 都是 miss；
- 在 `fsm2s -> fsmseq` 序列中，seed/active 都变成 hit。

这说明我们的缓存类比不是纯概念，而是能在系统日志中观察到：

1. warmup 任务把相关 skill 带进 L1；
2. 后续相邻任务复用 L1；
3. L1 hit 改变通过率和 ACPS；
4. 但 hit 的 utility 仍可能波动，需要进一步记录正负收益。

## 对用户想法的记录

本轮进一步支持你的几个核心设想：

1. skill 不应该一次性全部放进上下文，而应该像 cache line 一样按局部性进入 L1；
2. L1 hit/miss 必须可观察、可记录；
3. 任务局部性不仅有“问题语义局部性”，也有“时间局部性”；
4. 单任务 benchmark 可能破坏 cache 状态，因此论文实验要区分 cold-start probe 和 warmed-sequence probe；
5. 下一步需要把 hit 后收益写成 utility event，用于驱逐和降权。

## 下一步

1. 重复 `warmed_fsmseq` 至少 3 轮，验证时间局部性收益是否稳定。
2. 实现 per-skill utility event，记录每个 loaded skill 的 pass/fail、ACPS delta、timeout penalty。
3. 增加 utility-aware eviction：hit 后失败或 timeout 的 skill 降权，hit 后降低 ACPS 的 skill 升权。
4. 构造 `warmed_register`：用 `dff -> dff8` 验证 register 类 skill 为什么冷启动经常 miss。
