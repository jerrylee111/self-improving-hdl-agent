from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cache.retrieve import retrieve_skill_candidates
from harness.task_schema import HDLTask


@dataclass
class L1SkillCache:
    """Small per-run skill cache.

    Agents should receive only `entries`. External skill stores are accessed only by
    this cache layer.
    """

    capacity: int = 6
    agent: str = "coder"
    include_active: bool = True
    entries: list[dict[str, Any]] = field(default_factory=list)

    def lookup(self, task: HDLTask, *, policy: str) -> dict[str, Any]:
        hit_ids = [skill["id"] for skill in self.entries if _skill_matches_task(skill, task)]
        if hit_ids:
            return {
                "event": "l1_skill_cache_hit",
                "policy": policy,
                "l1_skill_ids": [skill["id"] for skill in self.entries],
                "hit_skill_ids": hit_ids,
                "miss": False,
                "retrieval": None,
            }

        retrieval = retrieve_skill_candidates(
            task,
            policy=policy,
            budget=self.capacity,
            agent=self.agent,
            include_active=self.include_active,
        )
        selected = retrieval["selected_skills"]
        self.entries = selected[: self.capacity]
        return {
            "event": "l1_skill_cache_miss",
            "policy": policy,
            "l1_skill_ids": [skill["id"] for skill in self.entries],
            "hit_skill_ids": [],
            "miss": True,
            "retrieval": retrieval,
        }


def _skill_matches_task(skill: dict[str, Any], task: HDLTask) -> bool:
    # Pinned or very generic skills are useful L1 residents, but they should not
    # by themselves prevent a miss when a new task needs more specific skills.
    task_terms = set(task.tags + [task.family, task.language, task.id])
    generic_terms = {"verilog", "systemverilog", "sequential", "combinational", "reset"}
    specific_terms = task_terms - generic_terms
    topics = set(skill.get("domain", {}).get("topic", []))
    patterns = " ".join(skill.get("task_patterns", [])).lower()
    if specific_terms & topics:
        return True
    return any(str(term).lower() in patterns for term in specific_terms)
