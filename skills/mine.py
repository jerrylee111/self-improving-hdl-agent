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


def mine_candidate_skill(
    task: HDLTask,
    *,
    policy: str,
    attempts: int,
    passed: bool,
    failure_summary: str,
    out_dir: Path = Path("skills/candidate"),
    events_path: Path = Path("skills/events/skill_events.jsonl"),
) -> dict[str, Any] | None:
    if not passed or attempts < 2:
        return None
    if "grant mismatch" in failure_summary and "arbiter" in task.family:
        name = "registered_round_robin_grant"
        payload = (
            "When an arbiter testbench samples grant after posedge clk, prefer registering grant "
            "and updating the priority pointer in the sequential block. A purely combinational "
            "grant derived from a priority bit that also updates on the same edge can expose the "
            "next-cycle priority too early."
        )
        topics = ["arbiter", "sequential", "fairness", "registered_output"]
        anti_patterns = ["combinational grant sampled after clock edge"]
    else:
        name = f"repair_pattern_{_slug(task.family)}"
        payload = (
            "A previous attempt failed and a later repair passed. Inspect the failed trace and "
            "preserve the timing semantics implied by the testbench when repairing similar tasks."
        )
        topics = list(dict.fromkeys(task.tags))
        anti_patterns = ["repeating a failed implementation without changing timing semantics"]

    skill_id = f"candidate.{_slug(task.id)}.{_slug(name)}.{int(time.time())}"
    candidate = {
        "id": skill_id,
        "name": name,
        "agent": "coder",
        "domain": {"language": task.language, "topic": topics},
        "task_patterns": [task.family, *task.tags],
        "preconditions": ["generated during task repair"],
        "anti_patterns": anti_patterns,
        "payload": {"type": "repair_pattern", "content": payload},
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
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = out_dir / f"{skill_id}.yaml"
    candidate_path.write_text(yaml.safe_dump(candidate, sort_keys=False))

    events_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event": "skill_candidate_generated",
        "skill_id": skill_id,
        "task_id": task.id,
        "policy": policy,
        "candidate_path": str(candidate_path),
        "source": "failure_then_repair",
    }
    with events_path.open("a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return candidate
