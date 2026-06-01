from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from agents.coder import generate_rtl
from agents.llm import LLMClient
from cache.retrieve import retrieve_skills
from harness.evaluate import evaluate_rtl
from harness.task_schema import HDLTask


def run_task_loop(
    task: HDLTask,
    *,
    policy: str,
    max_iters: int,
    out_dir: Path,
    llm: LLMClient,
) -> dict[str, Any]:
    skills = retrieve_skills(task, policy=policy)
    run_dir = out_dir / task.id
    start = time.time()
    previous_rtl: str | None = None
    feedback: str | None = None
    final_passed = False
    final_summary = ""
    attempts = 0

    for attempt in range(1, max_iters + 1):
        attempts = attempt
        rtl = generate_rtl(task, skills, llm, previous_rtl=previous_rtl, feedback=feedback)
        attempt_dir = run_dir / f"attempt_{attempt}"
        result = evaluate_rtl(task, rtl, attempt_dir)
        final_passed = result.passed
        final_summary = result.summary
        if result.passed:
            break
        previous_rtl = rtl
        feedback = result.summary[-6000:]

    return {
        "task_id": task.id,
        "source": task.source,
        "family": task.family,
        "tags": task.tags,
        "policy": policy,
        "retrieved_skills": [skill["id"] for skill in skills],
        "passed": final_passed,
        "iterations": attempts,
        "max_iters": max_iters,
        "wall_time_s": round(time.time() - start, 3),
        "workdir": str(run_dir),
        "failure_summary_tail": "" if final_passed else final_summary[-2000:],
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    solved = sum(1 for record in records if record["passed"])
    total_iterations = sum(record["iterations"] for record in records)
    failed = total - solved
    pass_at_k = solved / total if total else 0.0
    acps_iter = total_iterations / solved if solved else float("inf")
    ast_iter = solved / total_iterations if total_iterations else 0.0
    return {
        "tasks": total,
        "solved": solved,
        "failed": failed,
        "pass_at_k": round(pass_at_k, 4),
        "total_iterations": total_iterations,
        "acps_iter": round(acps_iter, 4) if solved else None,
        "ast_iter": round(ast_iter, 4),
    }
