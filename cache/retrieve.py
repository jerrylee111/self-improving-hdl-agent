from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness.task_schema import HDLTask


def load_seed_skills(path: Path = Path("skills/seed/rtl_rules.yaml")) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    return list(data.get("skills", []))


def load_active_skills(path: Path = Path("skills/active")) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for skill_path in sorted(path.glob("*.yaml")):
        data = yaml.safe_load(skill_path.read_text())
        if not data:
            continue
        if data.get("version", {}).get("status") == "active":
            skills.append(data)
    return skills


def load_skill_store(agent: str | None = None, include_active: bool = True) -> list[dict[str, Any]]:
    skills = [*load_seed_skills()]
    if include_active:
        skills.extend(load_active_skills())
    if agent is None:
        return skills
    return [
        skill
        for skill in skills
        if skill.get("agent", "both") in {agent, "both"}
    ]


def _score_skill(task: HDLTask, skill: dict[str, Any]) -> tuple[float, list[str]]:
    task_terms = set(task.tags + [task.family, task.language, task.id])
    reasons: list[str] = []
    if skill.get("cache", {}).get("pin"):
        return 100.0, ["pinned"]
    domain = skill.get("domain", {})
    topics = set(domain.get("topic", []))
    patterns = " ".join(skill.get("task_patterns", [])).lower()
    topic_hits = sorted(task_terms & topics)
    pattern_hits = sorted(term for term in task_terms if str(term).lower() in patterns)
    utility = float(skill.get("metrics", {}).get("utility_ema", 0.0))
    score = len(topic_hits) * 3.0
    score += len(pattern_hits)
    score += utility
    reasons.extend(f"topic:{hit}" for hit in topic_hits)
    reasons.extend(f"pattern:{hit}" for hit in pattern_hits)
    reasons.append(f"utility_ema:{utility:.2f}")
    return score, reasons


def retrieve_skill_candidates(
    task: HDLTask,
    policy: str = "fixed",
    budget: int = 6,
    agent: str | None = "coder",
    include_active: bool = True,
) -> dict[str, Any]:
    skills = load_skill_store(agent=agent, include_active=include_active)

    if policy == "no_skill":
        return {
            "policy": policy,
            "budget": budget,
            "candidate_count": len(skills),
            "candidates": [],
            "selected_skills": [],
            "evicted_skill_ids": [skill["id"] for skill in skills],
        }

    if policy == "fixed":
        # Fixed expert prompt baseline: stable ordering, no task-aware selection.
        selected = skills[:budget]
        selected_ids = {skill["id"] for skill in selected}
        candidates = [
            {
                "skill_id": skill["id"],
                "score": None,
                "selected": skill["id"] in selected_ids,
                "reasons": ["fixed_order"] if skill["id"] in selected_ids else ["beyond_budget"],
            }
            for skill in skills
        ]
        return {
            "policy": policy,
            "budget": budget,
            "candidate_count": len(skills),
            "candidates": candidates,
            "selected_skills": selected,
            "evicted_skill_ids": [skill["id"] for skill in skills if skill["id"] not in selected_ids],
        }

    ranked: list[tuple[float, list[str], dict[str, Any]]] = []
    for skill in skills:
        score, reasons = _score_skill(task, skill)
        ranked.append((score, reasons, skill))
    ranked.sort(key=lambda item: item[0], reverse=True)

    if policy == "tag_topk":
        selected = [skill for score, _, skill in ranked[: max(1, min(budget, 3))] if score > 0]

    elif policy == "locality_aware":
        selected = [skill for score, _, skill in ranked[:budget] if score > 0]
        if any(tag in task.tags for tag in ["sequential", "fsm", "valid_ready", "counter"]):
            selected.sort(
                key=lambda skill: (
                    "sequential" not in skill.get("domain", {}).get("topic", []),
                    "valid_ready" not in skill.get("domain", {}).get("topic", []),
                    skill["id"],
                )
            )
    else:
        raise ValueError(f"Unknown skill retrieval policy: {policy}")

    selected_ids = {skill["id"] for skill in selected}
    candidates = [
        {
            "skill_id": skill["id"],
            "score": round(score, 4),
            "selected": skill["id"] in selected_ids,
            "reasons": reasons if skill["id"] in selected_ids else reasons + ["evicted_by_budget_or_score"],
        }
        for score, reasons, skill in ranked
    ]
    return {
        "policy": policy,
        "budget": budget,
        "candidate_count": len(skills),
        "candidates": candidates,
        "selected_skills": selected,
        "evicted_skill_ids": [skill["id"] for _, _, skill in ranked if skill["id"] not in selected_ids],
    }


def retrieve_skills(
    task: HDLTask,
    policy: str = "fixed",
    budget: int = 6,
    agent: str | None = "coder",
    include_active: bool = True,
) -> list[dict[str, Any]]:
    return list(
        retrieve_skill_candidates(
            task,
            policy=policy,
            budget=budget,
            agent=agent,
            include_active=include_active,
        )["selected_skills"]
    )
