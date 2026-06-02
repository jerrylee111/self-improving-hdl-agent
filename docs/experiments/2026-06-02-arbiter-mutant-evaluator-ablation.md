# Arbiter Evaluator Mutant Kill 实验

日期：2026-06-02

## 实验动机

用户提出的核心观点是：coder skill 的目标是写对代码，而 evaluator skill 的目标应该是证明代码是错的。因此，仅报告 `passed` 或 `accepted_by_current_evaluator` 不够。我们还需要证明 evaluator skill 是否真的提高了“找错能力”。

本实验用 mutation testing 验证 evaluator skill 的收益。思路是准备一组人为注入 bug 的 arbiter RTL，然后比较旧 evaluator 和新 adversarial evaluator 能杀掉多少 mutant。

## 实验对象

任务：

`benchmarks/tasks/local_seed/round_robin_arbiter2.yaml`

Mutant 目录：

`benchmarks/mutants/round_robin_arbiter2/`

样本：

| 文件 | 类型 | 缺陷 |
| --- | --- | --- |
| `correct_registered.v` | correct | 注册输出、正确 round-robin |
| `bug_comb_grant_priority_leak.v` | mutant | 组合 grant 暴露 priority |
| `bug_no_alternation.v` | mutant | both-request 不交替 |
| `bug_idle_not_zero.v` | mutant | idle 时不清零 grant |
| `bug_reset_reentry_priority.v` | mutant | 二次 reset 不重置 priority |
| `bug_stateful_single_request_inactive.v` | mutant | 历史状态导致单请求时 grant 给未请求方 |
| `bug_both_onehot_violation_after_idle.v` | mutant | idle 后 both-request 输出 `2'b11` |

## Evaluator Profile

本实验比较两个 evaluator：

| profile | 描述 |
| --- | --- |
| `basic` | 旧版 directed test，只检查固定短序列 |
| `adversarial_v2` | 当前增强 evaluator，包含不变量检查、reset re-entry、覆盖检查和固定伪随机压力序列 |

`adversarial_v2` 对应 active evaluator skill：

`skills/active/skill.eval.arbiter.registered_grant_check.001.yaml`

其目标不是让 RTL 更容易通过，而是更积极地寻找反例。

## 实验命令

```bash
uv run python -m experiments.run_mutant_eval \
  --out-dir results/mutant_eval_current
```

同时执行代码编译检查：

```bash
uv run python -m py_compile agents/*.py cache/*.py harness/*.py experiments/*.py skills/*.py
```

结果：通过。

## 实验结果

结果文件：

`results/mutant_eval_current/round_robin_arbiter2/summary.json`

汇总：

| evaluator | mutants | killed | survived | mutant_kill_rate | correct_accepted |
| --- | ---: | ---: | ---: | ---: | --- |
| `basic` | 6 | 4 | 2 | 0.6667 | true |
| `adversarial_v2` | 6 | 6 | 0 | 1.0000 | true |

逐项结果：

| mutant | basic | adversarial_v2 |
| --- | --- | --- |
| `bug_both_onehot_violation_after_idle` | killed | killed |
| `bug_comb_grant_priority_leak` | killed | killed |
| `bug_idle_not_zero` | killed | killed |
| `bug_no_alternation` | killed | killed |
| `bug_reset_reentry_priority` | survived | killed |
| `bug_stateful_single_request_inactive` | survived | killed |

## 解释

旧 evaluator 的短 directed sequence 能抓住明显的 both-request 交替错误、idle 错误和组合 priority 泄漏，但它漏掉了两类更隐蔽的问题：

1. 二次 reset 不重置 priority。
2. 历史状态导致单请求时 grant 给未请求方。

新 adversarial evaluator 增加了 reset re-entry 检查和 `grant & ~req == 0` 不变量，因此能杀掉这两个旧 evaluator 放过的 mutant。

同时，正确设计 `correct_registered.v` 在两个 evaluator 下都被接受。这说明 evaluator v2 的增强没有在当前样本上造成误杀。

## 结论

本实验给出 evaluator skill 有效性的第一条定量证据：

```text
mutant_kill_rate: 0.6667 -> 1.0000
```

这支持用户提出的设计原则：evaluator skill 的收益应该用“发现更多错误”来衡量，而不是用“让任务更容易通过”来衡量。

需要注意，`adversarial_v2` 仍不构成完整正确性证明。它只是比旧 evaluator 更强，当前正确性声明仍然是：

```text
correctness_claim = not_proven
```

## 下一步

下一步可以把 mutation testing 扩展到更多任务族：

- FSM：错误状态转移、overlap detector、reset 状态错误。
- FIFO：full/empty 边界、同周期读写、指针 wrap。
- valid-ready：backpressure 下数据不稳定、ready/valid 组合环、吞吐丢拍。

当多个任务族都有 mutant kill rate 提升后，我们就能更系统地证明 evaluator skill cache 的价值。
