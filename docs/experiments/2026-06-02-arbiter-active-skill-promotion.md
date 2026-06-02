# Arbiter Candidate Skill 提升实验记录

日期：2026-06-02

本实验记录一次最小闭环：先让 `round_robin_arbiter2` 任务在缺少专门 arbiter skill 的情况下失败，再从失败信息中产生 coder/evaluator candidate skill，人工验证后提升为 active skill，最后重跑同一任务，观察 active skill 是否进入 L1，以及任务是否能从失败变为通过。

## 实验目的

本次实验要回答三个问题：

1. 失败信息是否会被转化为新的 candidate skill。
2. candidate skill 被验证并提升为 active 后，是否会通过 cache/retrieval 机制进入 L1。
3. active skill 进入 L1 后，同一个 arbiter 任务是否能从失败变成通过。

其中第 1、2 点用于验证 skill 生命周期和缓存链路，第 3 点用于验证 skill 对任务通过率的实际贡献。

## 任务

任务文件：

`benchmarks/tasks/local_seed/round_robin_arbiter2.yaml`

任务摘要：

- top module：`top_module`
- 类型：两请求者 round-robin arbiter
- 端口：`clk`、`reset`、`req[1:0]`、`grant[1:0]`
- 关键行为：当 `req == 2'b11` 时，在连续 granted cycle 中交替 grant requester 0 和 requester 1；reset 后 requester 0 优先。
- 验证方式：Verilator lint + Icarus Verilog simulation。

这个任务比简单组合逻辑更适合测试 skill 机制，因为它涉及“时序采样点”和“仲裁优先级状态”的对应关系。之前模型容易写出组合 `grant`，但 testbench 在 clock edge 之后采样，因此会暴露 next-cycle priority，导致 `grant mismatch`。

## 提升前结果

命令：

```bash
DEEPSEEK_TIMEOUT_S=90 DEEPSEEK_MAX_RETRIES=0 \
uv run python -m harness.run_task \
  benchmarks/tasks/local_seed/round_robin_arbiter2.yaml \
  --policy tag_topk \
  --no-dry-run \
  --max-iters 3 \
  --out-dir results/runs_current_test
```

结果文件：

`results/runs_current_test/local_round_robin_arbiter2/result.json`

核心结果：

| 字段 | 结果 |
| --- | --- |
| passed | `false` |
| iterations | `3` |
| policy | `tag_topk` |
| L1 event | `l1_skill_cache_miss` |
| loaded L1 skills | `skill.rtl.interface_exact.001`, `skill.rtl.seq_nonblocking.001`, `skill.rtl.comb_complete.001` |
| failure | `FATAL: tb.sv:9: grant mismatch` |

提升前，L1 中没有专门的 arbiter registered-grant skill。模型在三轮迭代后仍然没有修复 `grant mismatch`，因此这次失败被记录为一个完整 evaluator observation。

## 生成的 Candidate Skill

这次失败产生了两个 candidate skill：

| agent | candidate skill |
| --- | --- |
| coder | `candidate.local_round_robin_arbiter2.coder.registered_round_robin_grant.1780372184` |
| evaluator | `candidate.local_round_robin_arbiter2.evaluator.arbiter_registered_grant_check.1780372184` |

对应文件：

- `skills/candidate/candidate.local_round_robin_arbiter2.coder.registered_round_robin_grant.1780372184.yaml`
- `skills/candidate/candidate.local_round_robin_arbiter2.evaluator.arbiter_registered_grant_check.1780372184.yaml`

事件日志：

`skills/events/skill_events.jsonl`

这里的关键设计是：失败本身就是完整信息，不需要等到“失败后又成功”才生成 skill。evaluator 观察到失败后，分别产生：

- coder skill：提示 coder 在这种 arbiter/testbench 关系下，应优先注册 `grant`，不要让同一 clock edge 更新的 priority 立即泄漏到组合输出。
- evaluator skill：提示 evaluator 对 round-robin arbiter 应持续保持两个 request 为 high，并在 clock edge 后采样 grant。

## 验证与提升

本次使用人工验证方式提升 candidate skill。验证依据是 candidate payload 与已观察失败签名直接对应：

- 失败签名：`grant mismatch`
- 失败触发位置：`tb.sv:9`
- 失败原因判断：testbench 在 posedge 后采样，组合 grant 可能暴露 next-cycle priority。

提升后的 active skill：

| agent | active skill |
| --- | --- |
| coder | `skill.rtl.arbiter.registered_round_robin_grant.001` |
| evaluator | `skill.eval.arbiter.registered_grant_check.001` |

对应文件：

- `skills/active/skill.rtl.arbiter.registered_round_robin_grant.001.yaml`
- `skills/active/skill.eval.arbiter.registered_grant_check.001.yaml`

两个 active skill 都带有 `validation.evidence`，并记录了 `manual_promote_for_ablation` 决策。也就是说，promotion 是一个可观察的生命周期状态变化，而不是把 candidate 文件静默加入 prompt。

## Promotion 后的检索验证

先运行编译检查：

```bash
uv run python -m py_compile agents/*.py cache/*.py harness/*.py experiments/*.py skills/*.py
```

结果：通过。

随后直接检查同一任务在 `tag_topk` 下的检索结果：

```bash
uv run python - <<'PY'
from pathlib import Path
from harness.task_schema import load_task
from cache.retrieve import retrieve_skill_candidates

task = load_task(Path('benchmarks/tasks/local_seed/round_robin_arbiter2.yaml'))
for agent in ['coder', 'evaluator']:
    r = retrieve_skill_candidates(task, policy='tag_topk', budget=3, agent=agent)
    print(agent, [s['id'] for s in r['selected_skills']])
PY
```

结果：

| agent | selected skills |
| --- | --- |
| coder | `skill.rtl.interface_exact.001`, `skill.rtl.arbiter.registered_round_robin_grant.001`, `skill.rtl.seq_nonblocking.001` |
| evaluator | `skill.eval.arbiter.registered_grant_check.001` |

这个结果说明两件事：

1. coder 不会看到 evaluator 的 active skill。
2. evaluator 不会看到 coder 的 active skill。

也就是说，外部 store 里虽然存在多个 agent 的 skill，但 agent 自身只接收 L1 中属于自己的 skill。这个行为更接近我们想要的 cache 边界：agent 不直接遍历全量 skill store，而是由 cache/retrieval 层完成 miss 后的选择、加载和驱逐。

## Promotion 后重跑 Arbiter

命令：

```bash
DEEPSEEK_TIMEOUT_S=120 DEEPSEEK_MAX_RETRIES=0 \
uv run python -m harness.run_task \
  benchmarks/tasks/local_seed/round_robin_arbiter2.yaml \
  --policy tag_topk \
  --no-dry-run \
  --max-iters 3 \
  --out-dir results/runs_active_promotion
```

第一次结果文件：

`results/runs_active_promotion/local_round_robin_arbiter2/result.json`

核心结果：

| 字段 | 结果 |
| --- | --- |
| passed | `false` |
| iterations | `1` |
| policy | `tag_topk` |
| L1 event | `l1_skill_cache_miss` |
| loaded L1 skills | `skill.rtl.interface_exact.001`, `skill.rtl.arbiter.registered_round_robin_grant.001`, `skill.rtl.seq_nonblocking.001` |
| failure | `LLM call failed: APIConnectionError: Connection error.` |

这次 no-dry-run 重跑确认了 active coder skill 已经进入 L1，但没有进入 Verilog 生成和仿真阶段，因此不能判定“任务是否从失败变成通过”。

这里需要明确区分两类失败：

| 阶段 | 失败类型 | 是否反映 skill/cache 效果 |
| --- | --- | --- |
| 提升前 | HDL 仿真失败，`grant mismatch` | 是 |
| 提升后 | LLM API 连接失败 | 否 |

因此，本次实验对第 1、2 个问题给出正向结果，对第 3 个问题暂时给出不可判定结果。

## Promotion 后重试结果

为了排除第一次 no-dry-run 的外部 API 连接问题，使用同一 active skill store 再跑一次：

```bash
DEEPSEEK_TIMEOUT_S=180 DEEPSEEK_MAX_RETRIES=1 \
uv run python -m harness.run_task \
  benchmarks/tasks/local_seed/round_robin_arbiter2.yaml \
  --policy tag_topk \
  --no-dry-run \
  --max-iters 3 \
  --out-dir results/runs_active_promotion_retry
```

结果文件：

`results/runs_active_promotion_retry/local_round_robin_arbiter2/result.json`

核心结果：

| 字段 | 结果 |
| --- | --- |
| passed / accepted_by_current_evaluator | `true` |
| iterations | `2` |
| policy | `tag_topk` |
| L1 event | `l1_skill_cache_miss` |
| loaded L1 skills | `skill.rtl.interface_exact.001`, `skill.rtl.arbiter.registered_round_robin_grant.001`, `skill.rtl.seq_nonblocking.001` |
| correctness_claim | `not_proven` |
| workdir | `results/runs_active_promotion_retry/local_round_robin_arbiter2` |

这次运行确认了当前 evaluator 下的完整链路：

`failure -> candidate skill -> validated active skill -> L1 retrieval -> iterative repair -> pass`

注意，这次最终被当前 evaluator 接受用了 2 次迭代。也就是说，active arbiter skill 没有让模型在第一轮必然一次成功，但它进入 L1 后，模型在 evaluator feedback 的帮助下完成了修复。按当前定义，任务的 `accepted_by_current_evaluator@3 = 1`，平均接受迭代数 `iterations_to_acceptance = 2`。这不是完整正确性证明，仍应记录 `correctness_claim = not_proven`。

这次运行还生成了两个新的 candidate skill：

- `candidate.local_round_robin_arbiter2.coder.repair_pattern_sequential_arbiter.1780385584`
- `candidate.local_round_robin_arbiter2.evaluator.check_pattern_sequential_arbiter.1780385584`

原因是第一轮尝试仍然留下了失败反馈；即使最终第二轮通过，第一轮失败也仍然是可挖掘的信息。后续需要为这类“最终通过但中间失败”的 candidate 加上去重和合并策略，避免同类 arbiter skill 重复膨胀。

## 当前结论

本次实验已经验证：

1. evaluator 观察到失败后，可以生成 coder/evaluator 两类 candidate skill。
2. candidate skill 可以带验证证据后提升为 active skill。
3. active skill 会参与外部 store 检索，并在 L1 miss 后被加载进 L1。
4. agent 侧存在 agent-aware filtering，coder/evaluator 不会看到彼此不属于自己的 skill。
5. 在一次成功的 LLM 调用中，active skill 进入 L1 后，`round_robin_arbiter2` 可以从提升前的 `grant mismatch` 失败变成被当前 evaluator 接受。

第一次 promotion 后 no-dry-run 受到 `APIConnectionError` 影响，没有产生 RTL，也没有进入 evaluator simulation，因此它应记为 external LLM call inconclusive，而不是 skill-cache negative result。第二次 retry 才是本实验中有效的 pass/fail 判定。

## 下一步

下一步不再是确认单个 arbiter 能否通过，而是把这个结果扩展成小规模 ablation：

- 对比提升前后 `round_robin_arbiter2` 的 `pass@3` 和 `iterations_to_success`。
- 在相近 sequential arbiter/FSM 任务上测试这个 active skill 是否有迁移收益。
- 给 candidate skill 增加去重、合并和版本更新逻辑，避免中间失败反复生成语义相同的 skill。
- 单独记录 external API failure，不把它混入 HDL failure 和 skill-cache failure。
