from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness.task_schema import HDLTask


def load_seed_skills(path: Path = Path("skills/seed/rtl_rules.yaml")) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    return list(data.get("skills", []))


def retrieve_skills(task: HDLTask, budget: int = 6) -> list[dict[str, Any]]:
    skills = load_seed_skills()
    task_terms = set(task.tags + [task.family, task.language, task.id])
    ranked: list[tuple[float, dict[str, Any]]] = []
    for skill in skills:
        if skill.get("cache", {}).get("pin"):
            score = 100.0
        else:
            domain = skill.get("domain", {})
            topics = set(domain.get("topic", []))
            patterns = " ".join(skill.get("task_patterns", [])).lower()
            score = len(task_terms & topics) * 3.0
            score += sum(1 for term in task_terms if str(term).lower() in patterns)
            score += float(skill.get("metrics", {}).get("utility_ema", 0.0))
        ranked.append((score, skill))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [skill for score, skill in ranked[:budget] if score > 0]
