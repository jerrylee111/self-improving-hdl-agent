# 阶段性工作报告：Evaluator 作为对抗式验证者

日期：2026-06-02

## 用户提出的关键想法

用户指出：当前 evaluator 通过，只是从 evaluator 当前能力角度看没有发现错误；这不等于 RTL 满足完整规格。coder skill 的目标应该是写对代码，而 evaluator skill 的目标不应该是帮助代码通过测试，而应该是尽可能证明代码是错误的。

这条想法改变了系统的评价语义：

- coder 是设计者，目标是生成满足规格的 RTL。
- evaluator 是对抗式验证者，目标是寻找反例、漏洞、未覆盖 corner case 和规格不一致证据。
- `passed: true` 只能表示“被当前 evaluator 接受”，不能表示“代码正确”。

## 对系统设计的影响

我们需要避免把 evaluator 当成 approval agent。更准确的闭环应该是：

```text
task spec
  -> coder 生成 RTL
  -> evaluator 尝试证明 RTL 错误
  -> 若找到反例，返回 counterexample/失败签名
  -> coder 修复
  -> evaluator 升级攻击策略
```

因此，skill 演化也应分裂为两个目标：

| agent | skill 目标 | 成功信号 |
| --- | --- | --- |
| coder | 更可能生成满足规格的 RTL | 在更强 evaluator 下仍被接受 |
| evaluator | 更容易找到 RTL 错误 | 发现反例、覆盖新 corner case、构造更强 assertion |

## 本阶段实现更新

本阶段对结果记录做了语义修正：

- 保留 `passed` 字段，用于兼容现有脚本。
- 新增 `accepted_by_current_evaluator`，明确表示当前 evaluator 没有发现错误。
- 新增 `correctness_claim: not_proven`，避免把仿真通过误写成正确性证明。
- 新增 `evaluator_goal: find_counterexample_or_bug`，记录 evaluator 的目标是找错。
- 新增 `evaluator_strength`，记录当前 evaluator 使用了哪些检查能力。

示例输出：

```json
{
  "passed": true,
  "accepted_by_current_evaluator": true,
  "correctness_claim": "not_proven",
  "evaluator_goal": "find_counterexample_or_bug",
  "evaluator_strength": {
    "lint": true,
    "directed_simulation": true,
    "random_simulation": false,
    "reference_model": true,
    "assertions": false,
    "formal": false,
    "coverage": null,
    "correctness_claim": "not_proven"
  }
}
```

## 对论文指标的影响

后续不能只报告 `pass@k`。应至少同时报告：

- `accepted_by_current_evaluator@k`：当前 evaluator 下的接受率。
- `counterexample_found_rate`：evaluator 找到反例的比例。
- `evaluator_strength_score`：lint、directed simulation、random simulation、assertions、formal、coverage 的组合强度。
- `robust_acceptance_rate`：在更强 evaluator 或隐藏测试下仍被接受的比例。
- `iterations_to_acceptance`：被当前 evaluator 接受所需的平均迭代次数。

其中 `accepted_by_current_evaluator@k` 对应旧的 `pass@k`，但名称更准确。

## 下一步

下一阶段应优先增强 evaluator，而不是只增强 coder：

1. 为 arbiter/FSM/FIFO/valid-ready 等任务生成 adversarial evaluator skill。
2. 在 testbench 中加入 directed corner cases 和简单 randomized tests。
3. 对适合的小模块加入 SystemVerilog assertions。
4. 将 evaluator skill 的收益定义为“发现了旧 evaluator 找不到的 bug”。
5. 在实验报告中区分 evaluator 接受、隐藏测试通过、形式化证明三种不同强度的正确性证据。

## 后续实现进展

本阶段继续向 adversarial evaluator 推进，先以 `local_round_robin_arbiter2` 为试点增强本地 evaluator：

- 在 testbench 中加入 onehot0 检查。
- 检查 `grant & ~req == 0`，防止 grant 给未请求方。
- 检查 idle cycle 必须 `grant == 0`。
- 检查 reset re-entry 后 priority 重新从 requester 0 开始。
- 检查 both-request 场景必须覆盖 requester 0 和 requester 1。
- 加入固定伪随机 `req` 压力序列，用于扩大当前 evaluator 的输入探索范围。

同时更新 active evaluator skill：

`skills/active/skill.eval.arbiter.registered_grant_check.001.yaml`

该 skill 的 revision 从 1 更新到 2，payload 从“持续保持 both requests high”扩展为“对抗式 arbiter verifier”，包含不变量、reset re-entry、覆盖要求和压力序列。

## 本地验证

执行代码编译检查：

```bash
uv run python -m py_compile agents/*.py cache/*.py harness/*.py experiments/*.py skills/*.py
```

结果：通过。

随后用旧实验产物做正负例验证：

| case | RTL 来源 | 结果 |
| --- | --- | --- |
| old failed design | `results/runs_current_test/local_round_robin_arbiter2/attempt_3/design.v` | rejected，仍触发 `grant mismatch` |
| old accepted design | `results/runs_active_promotion_retry/local_round_robin_arbiter2/attempt_2/design.v` | accepted |

这说明增强后的 evaluator 没有只是改变报告字段，而是真的在 testbench 中加入了更强的检查；同时它没有误杀之前已经修复的 arbiter RTL。

当前 evaluator strength 记录为：

```json
{
  "lint": true,
  "directed_simulation": true,
  "random_simulation": true,
  "reference_model": true,
  "assertions": true,
  "formal": false,
  "coverage": null,
  "correctness_claim": "not_proven"
}
```

需要注意，这里的 `assertions` 目前是 testbench 内的即时不变量检查，不是完整 SVA/formal property；`random_simulation` 是固定种子的伪随机压力序列。它们提高了 evaluator 的找错能力，但仍不构成完整正确性证明。
