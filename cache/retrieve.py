from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness.task_schema import HDLTask


def load_seed_skills(path: Path = Path("skills/seed/rtl_rules.yaml")) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    return list(data.get("skills", []))


def _score_skill(task: HDLTask, skill: dict[str, Any]) -> float:
    task_terms = set(task.tags + [task.family, task.language, task.id])
    if skill.get("cache", {}).get("pin"):
        return 100.0
    domain = skill.get("domain", {})
    topics = set(domain.get("topic", []))
    patterns = " ".join(skill.get("task_patterns", [])).lower()
    score = len(task_terms & topics) * 3.0
    score += sum(1 for term in task_terms if str(term).lower() in patterns)
    score += float(skill.get("metrics", {}).get("utility_ema", 0.0))
    return score


def retrieve_skills(task: HDLTask, policy: str = "fixed", budget: int = 6) -> list[dict[str, Any]]:
    skills = load_seed_skills()

    if policy == "no_skill":
        return []

    if policy == "fixed":
        # Fixed expert prompt baseline: stable ordering, no task-aware selection.
        return skills[:budget]

    ranked: list[tuple[float, dict[str, Any]]] = []
    for skill in skills:
        score = _score_skill(task, skill)
        ranked.append((score, skill))
    ranked.sort(key=lambda item: item[0], reverse=True)

    if policy == "tag_topk":
        return [skill for score, skill in ranked[: max(1, min(budget, 3))] if score > 0]

    if policy == "locality_aware":
        selected = [skill for score, skill in ranked[:budget] if score > 0]
        if any(tag in task.tags for tag in ["sequential", "fsm", "valid_ready", "counter"]):
            selected.sort(
                key=lambda skill: (
                    "sequential" not in skill.get("domain", {}).get("topic", []),
                    "valid_ready" not in skill.get("domain", {}).get("topic", []),
                    skill["id"],
                )
            )
        return selected

    raise ValueError(f"Unknown skill retrieval policy: {policy}")
