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
        topics = list(dict.fromkeys(task.tags))
        anti_patterns = ["repeating a failed implementation without addressing the failure signature"]
        specs = [
            (
                "coder",
                f"repair_pattern_{_slug(task.family)}",
                "The evaluator observed a failure. Use the failure signature to repair the specific "
                "timing, width, reset, or protocol behavior instead of repeating the same implementation.",
            ),
            (
                "evaluator",
                f"check_pattern_{_slug(task.family)}",
                "Preserve this failure signature as a regression check for similar tasks. Emphasize the "
                "observed mismatch class when generating future tests.",
            ),
        ]

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
