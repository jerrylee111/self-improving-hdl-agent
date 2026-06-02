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

        retrieval = retrieve_skill_candidates(task, policy=policy, budget=self.capacity)
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
    if skill.get("cache", {}).get("pin"):
        return True
    task_terms = set(task.tags + [task.family, task.language, task.id])
    topics = set(skill.get("domain", {}).get("topic", []))
    patterns = " ".join(skill.get("task_patterns", [])).lower()
    if task_terms & topics:
        return True
    return any(str(term).lower() in patterns for term in task_terms)
