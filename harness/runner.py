from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from agents.coder import generate_rtl
from agents.llm import LLMClient
from cache.skill_cache import L1SkillCache
from harness.evaluate import evaluate_rtl
from harness.task_schema import HDLTask
from skills.mine import mine_candidate_skills_from_failure


def run_task_loop(
    task: HDLTask,
    *,
    policy: str,
    max_iters: int,
    out_dir: Path,
    llm: LLMClient,
    skill_cache: L1SkillCache | None = None,
) -> dict[str, Any]:
    skill_cache = skill_cache or L1SkillCache()
    cache_event = skill_cache.lookup(task, policy=policy)
    skills = list(skill_cache.entries)
    run_dir = out_dir / task.id
    start = time.time()
    previous_rtl: str | None = None
    feedback: str | None = None
    final_passed = False
    final_summary = ""
    first_failure_summary = ""
    attempts = 0

    for attempt in range(1, max_iters + 1):
        attempts = attempt
        try:
            rtl = generate_rtl(task, skills, llm, previous_rtl=previous_rtl, feedback=feedback)
        except Exception as exc:
            final_summary = f"LLM call failed: {type(exc).__name__}: {exc}"
            break
        attempt_dir = run_dir / f"attempt_{attempt}"
        result = evaluate_rtl(task, rtl, attempt_dir)
        final_passed = result.passed
        final_summary = result.summary
        if (not result.passed) and not first_failure_summary:
            first_failure_summary = result.summary
        if result.passed:
            break
        previous_rtl = rtl
        feedback = result.summary[-6000:]

    candidate_skills = mine_candidate_skills_from_failure(
        task,
        policy=policy,
        attempts=attempts,
        failure_summary=first_failure_summary,
    )

    return {
        "task_id": task.id,
        "source": task.source,
        "family": task.family,
        "tags": task.tags,
        "policy": policy,
        "retrieved_skills": [skill["id"] for skill in skills],
        "l1_skill_ids": [skill["id"] for skill in skills],
        "skill_cache_event": cache_event["event"],
        "skill_cache_miss": cache_event["miss"],
        "skill_retrieval": {
            "policy": policy,
            "budget": skill_cache.capacity,
            "candidate_count": 0 if cache_event["retrieval"] is None else cache_event["retrieval"]["candidate_count"],
            "candidates": [] if cache_event["retrieval"] is None else cache_event["retrieval"]["candidates"],
            "evicted_skill_ids": [] if cache_event["retrieval"] is None else cache_event["retrieval"]["evicted_skill_ids"],
        },
        "passed": final_passed,
        "iterations": attempts,
        "max_iters": max_iters,
        "wall_time_s": round(time.time() - start, 3),
        "workdir": str(run_dir),
        "failure_summary_tail": "" if final_passed else final_summary[-2000:],
        "candidate_skills_generated": [skill["id"] for skill in candidate_skills],
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    solved = sum(1 for record in records if record["passed"])
    api_failures = sum(
        1
        for record in records
        if (not record["passed"]) and "LLM call failed" in record.get("failure_summary_tail", "")
    )
    total_iterations = sum(record["iterations"] for record in records)
    failed = total - solved
    hdl_failed = failed - api_failures
    pass_at_k = solved / total if total else 0.0
    acps_iter = total_iterations / solved if solved else float("inf")
    ast_iter = solved / total_iterations if total_iterations else 0.0
    return {
        "tasks": total,
        "solved": solved,
        "failed": failed,
        "hdl_failed": hdl_failed,
        "api_failures": api_failures,
        "pass_at_k": round(pass_at_k, 4),
        "total_iterations": total_iterations,
        "acps_iter": round(acps_iter, 4) if solved else None,
        "ast_iter": round(ast_iter, 4),
    }
