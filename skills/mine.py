from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yaml

from harness.task_schema import HDLTask


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _candidate(
    task: HDLTask,
    *,
    skill_id: str,
    name: str,
    agent: str,
    topics: list[str],
    anti_patterns: list[str],
    payload: str,
    policy: str,
    attempts: int,
    failure_summary: str,
) -> dict[str, Any]:
    return {
        "id": skill_id,
        "name": name,
        "agent": agent,
        "domain": {"language": task.language, "topic": topics},
        "task_patterns": [task.family, *task.tags],
        "preconditions": ["generated from evaluator-observed failure"],
        "anti_patterns": anti_patterns,
        "payload": {"type": "repair_pattern" if agent == "coder" else "test_strategy", "content": payload},
        "metrics": {"uses": 0, "successes": 0, "failures": 0, "utility_ema": 0.0, "token_cost_ema": 0.0},
        "cache": {"pin": False},
        "version": {"status": "candidate", "revision": 1, "parent_ids": []},
        "validation": {
            "evidence": [
                {
                    "task_id": task.id,
                    "policy": policy,
                    "attempts": attempts,
                    "failure_signature": failure_summary[-500:],
                }
            ]
        },
    }


def _failure_observation(task: HDLTask, failure_summary: str) -> dict[str, str | int | None]:
    output_match = re.search(
        r"Output '([^']+)' has (\d+) mismatches\. First mismatch occurred at time (\d+)",
        failure_summary,
    )
    total_match = re.search(r"Mismatches:\s+(\d+)\s+in\s+(\d+)\s+samples", failure_summary)
    compile_failed = "error:" in failure_summary.lower() and "Mismatches:" not in failure_summary
    return {
        "failure_kind": "simulation_mismatch" if total_match else ("compile_or_lint_failure" if compile_failed else "unknown"),
        "output": output_match.group(1) if output_match else None,
        "first_mismatch_time": int(output_match.group(3)) if output_match else None,
        "mismatches": int(total_match.group(1)) if total_match else None,
        "samples": int(total_match.group(2)) if total_match else None,
        "family": task.family,
    }


def _generic_specs(task: HDLTask, failure_summary: str) -> tuple[list[str], list[str], list[tuple[str, str, str]]]:
    observation = _failure_observation(task, failure_summary)
    topics = list(dict.fromkeys(task.tags))
    anti_patterns = ["repeating a failed implementation without addressing the failure signature"]
    output = observation["output"] or "the failing output"
    mismatch_note = (
        f"The observed failure was {observation['mismatches']} mismatches out of "
        f"{observation['samples']} samples on output {output}, first seen at time "
        f"{observation['first_mismatch_time']}."
        if observation["mismatches"] is not None
        else "The observed failure was reported by the evaluator; preserve the exact signature."
    )

    if task.family.startswith("sequential"):
        coder_payload = (
            f"{mismatch_note} For similar sequential tasks, repair by checking reset value, "
            "posedge update order, nonblocking assignments, enable conditions, terminal-count behavior, "
            "and whether outputs should reflect the current state or the next state."
        )
        evaluator_payload = (
            f"{mismatch_note} For similar sequential tasks, add regression stimuli around reset release, "
            "first active cycle, terminal-count or wrap cycles, and consecutive enabled cycles. Compare "
            "the named output cycle-by-cycle against a reference model."
        )
    elif "mux" in task.family:
        coder_payload = (
            f"{mismatch_note} For similar mux tasks, verify select bit ordering, vector part-select bounds, "
            "and default behavior for all select values."
        )
        evaluator_payload = (
            f"{mismatch_note} For similar mux tasks, sweep every select value and include distinct data "
            "patterns so bit-order inversions cannot pass."
        )
    else:
        coder_payload = (
            f"{mismatch_note} Repair the exact expression, width, polarity, and concatenation order before "
            "changing unrelated structure."
        )
        evaluator_payload = (
            f"{mismatch_note} Preserve a regression that toggles each input independently and uses asymmetric "
            "patterns to catch polarity, width, and ordering mistakes."
        )

    return topics, anti_patterns, [
        ("coder", f"repair_pattern_{_slug(task.family)}", coder_payload),
        ("evaluator", f"check_pattern_{_slug(task.family)}", evaluator_payload),
    ]


def mine_candidate_skills_from_failure(
    task: HDLTask,
    *,
    policy: str,
    attempts: int,
    failure_summary: str,
    out_dir: Path = Path("skills/candidate"),
    events_path: Path = Path("skills/events/skill_events.jsonl"),
) -> list[dict[str, Any]]:
    """Generate coder/evaluator candidate skills as soon as evaluator observes a failure."""
    if not failure_summary:
        return []

    if "grant mismatch" in failure_summary and "arbiter" in task.family:
        topics = ["arbiter", "sequential", "fairness", "registered_output"]
        anti_patterns = ["combinational grant sampled after clock edge"]
        specs = [
            (
                "coder",
                "registered_round_robin_grant",
                "When an arbiter testbench samples grant after posedge clk, prefer registering grant "
                "and updating the priority pointer in the sequential block. A purely combinational "
                "grant derived from a priority bit that also updates on the same edge can expose the "
                "next-cycle priority too early.",
            ),
            (
                "evaluator",
                "arbiter_registered_grant_check",
                "For round-robin arbiters, include tests that hold both requests high across multiple "
                "clock cycles and sample grant after the clock edge. This catches designs that expose "
                "next-cycle priority through a combinational grant.",
            ),
        ]
    else:
        topics, anti_patterns, specs = _generic_specs(task, failure_summary)

    out_dir.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    candidates: list[dict[str, Any]] = []
    with events_path.open("a") as f:
        for agent, name, payload in specs:
            skill_id = f"candidate.{_slug(task.id)}.{agent}.{_slug(name)}.{timestamp}"
            candidate = _candidate(
                task,
                skill_id=skill_id,
                name=name,
                agent=agent,
                topics=topics,
                anti_patterns=anti_patterns,
                payload=payload,
                policy=policy,
                attempts=attempts,
                failure_summary=failure_summary,
            )
            candidate_path = out_dir / f"{skill_id}.yaml"
            candidate_path.write_text(yaml.safe_dump(candidate, sort_keys=False))
            event = {
                "event": "skill_candidate_generated",
                "skill_id": skill_id,
                "task_id": task.id,
                "policy": policy,
                "candidate_path": str(candidate_path),
                "source": "failure_observed",
                "agent": agent,
            }
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            candidates.append(candidate)
    return candidates


def mine_candidate_skill(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    candidates = mine_candidate_skills_from_failure(*args, **kwargs)
    return candidates[0] if candidates else None
