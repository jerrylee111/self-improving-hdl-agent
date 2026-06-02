# Skill 生成、提取与可观测性设计

## 1. 当前状态判断

当前系统的 skill 提取还不完整。

已经有的部分：

- 外部 seed skill 文件：`skills/seed/rtl_rules.yaml`
- 简单 task-aware retrieval：`no_skill`、`fixed`、`tag_topk`、`locality_aware`
- 实验记录中保存 `retrieved_skills`

缺失的关键部分：

- 没有记录候选 skill 集合。
- 没有记录每个 skill 的分数、命中原因和被驱逐原因。
- 没有记录 skill 是否真的被 coder 使用。
- 没有任务结束后的 skill mining。
- 没有 candidate skill 验证、入库、版本管理。
- 没有 skill usage metrics 更新。

因此，目前的 skill retrieval 只能算第一版 baseline，不是完整的 skill cache。

## 2. 我们需要观察什么

要证明“skill 是任务过程中不断生成和提取的”，每个 task run 必须留下完整轨迹。

### 2.1 提取过程可观测

每次 retrieval 应记录：

```json
{
  "event": "skill_retrieval",
  "task_id": "local_round_robin_arbiter2",
  "policy": "tag_topk",
  "budget": 3,
  "candidate_count": 6,
  "candidates": [
    {
      "skill_id": "skill.rtl.seq_nonblocking.001",
      "score": 7.95,
      "selected": true,
      "reasons": ["topic:sequential", "pattern:reset", "utility_ema:0.95"]
    }
  ],
  "selected_skill_ids": ["..."],
  "evicted_skill_ids": ["..."]
}
```

这样我们能回答：

- 哪些 skill 被考虑过？
- 为什么选中某个 skill？
- 为什么另一个 skill 没有进入上下文？
- 当前策略是否真的符合“时间局部性/问题局部性”？

### 2.2 使用过程可观测

每次 coder 调用应记录：

- prompt 中实际注入的 skill ids。
- 每个 skill 的 token 估计成本。
- coder 是否在输出解释或修复中引用了 skill。
- 该 skill 所在任务是否最终通过。

第一版可以先用弱观测：

```json
{
  "event": "skill_usage",
  "task_id": "...",
  "attempt": 1,
  "in_context_skill_ids": ["..."],
  "passed_after_attempt": true
}
```

后续再增加强观测：

- 要求 coder 输出 `skills_applied`。
- 或由 evaluator/LLM judge 判断某 skill 是否被实际应用。

### 2.3 生成过程可观测

每个任务结束后，skill miner 应产生候选 skill，记录：

```json
{
  "event": "skill_candidate_generated",
  "task_id": "local_round_robin_arbiter2",
  "source": "failure_then_repair",
  "candidate": {
    "name": "registered_round_robin_grant",
    "agent": "coder",
    "domain": {"topic": ["arbiter", "sequential", "fairness"]},
    "task_patterns": ["round-robin arbiter", "registered grant"],
    "anti_patterns": ["combinational grant sampled after clock edge"],
    "payload": {
      "type": "repair_pattern",
      "content": "When a testbench samples grant after posedge clk, register grant and update the priority pointer in the same sequential block."
    }
  },
  "evidence": {
    "failed_attempt": 1,
    "passed_attempt": 2,
    "failure_signature": "grant mismatch"
  },
  "status": "candidate"
}
```

这样我们能证明：

- skill 不是人工静态写死的。
- 它来自任务失败、修复和 evaluator 反馈。
- 它带有证据和触发条件。

### 2.4 验证过程可观测

Candidate skill 不能直接进入 active store。必须记录验证：

```json
{
  "event": "skill_validation",
  "candidate_id": "candidate.rtl.arbiter.registered_grant.001",
  "validation_tasks": ["..."],
  "baseline_pass": 0.5,
  "with_skill_pass": 0.75,
  "delta_acps": -0.3,
  "decision": "accept | reject | needs_more_data"
}
```

## 3. Skill 生命周期

建议使用以下状态机：

```text
observed_failure_or_success
  -> skill_candidate_generated
  -> candidate
  -> validation_pending
  -> active | rejected | deprecated
```

每个状态变化都写入 `skill_events.jsonl`。

## 4. 目录设计

```text
skills/
  seed/
  active/
  candidate/
  rejected/
  events/
    skill_events.jsonl
  metrics/
    skill_metrics.json
```

实验运行产物：

```text
results/experiments/<run_name>/
  records.jsonl
  summary.json
  skill_trace.jsonl
  artifacts/
```

## 5. 当前 retrieval 完整性评估

当前 retrieval 的完整性：

| 能力 | 当前状态 |
| --- | --- |
| 外部 skill store | 部分完成，只有 seed YAML |
| 候选 skill 打分 | 部分完成，只有简单 topic/pattern/utility |
| 提取 trace | 未完成 |
| cache admission | 未完成 |
| cache eviction | 未完成 |
| 时间局部性 | 未完成 |
| 空间/问题局部性 | 部分完成，使用 tags/topics |
| 使用反馈更新 metrics | 未完成 |
| 自动生成 candidate skill | 未完成 |
| candidate validation | 未完成 |

结论：

> 现在的 skill 提取不是完整 cache，只是检索 baseline。下一阶段应优先补 retrieval trace、skill candidate mining 和 metrics update。

## 6. 最小可实现版本

下一步不需要一次性实现完整自进化。建议先做最小闭环：

1. Retrieval trace：
   - 记录候选 skill。
   - 记录 score。
   - 记录 selected/evicted。
2. Failure-to-skill mining：
   - 如果某任务先失败后成功，生成 candidate skill。
   - 先用规则模板生成，不必完全依赖 LLM。
3. Candidate store：
   - 写入 `skills/candidate/*.yaml`。
   - 写入 `skills/events/skill_events.jsonl`。
4. Manual validation：
   - 暂时人工或脚本选择是否提升为 active。
5. Experiment report：
   - 报告每轮新增 skill 数量、被选次数、成功关联次数。

## 7. 对论文的意义

有了这些 trace 后，论文可以不只报告最终 pass rate，还可以展示：

- 某类任务触发了哪些 skill。
- 某个失败如何演化成 candidate skill。
- candidate skill 如何在后续任务中被命中。
- cache policy 如何选择/驱逐 skill。
- skill memory 随时间增长时，context 中实际进入的是哪些知识。
