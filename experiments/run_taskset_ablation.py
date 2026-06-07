from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import typer
import yaml
from rich.console import Console
from rich.table import Table

from agents.llm import LLMClient
from cache.skill_cache import L1SkillCache
from harness.runner import run_task_loop, summarize_records
from harness.task_schema import load_task

app = typer.Typer(help="Run task-set ablations while preserving L1 cache within each condition.")
console = Console()


def _hard_timeout_record(
    *,
    task_path: Path,
    condition_id: str,
    task_index: int,
    policy: str,
    max_iters: int,
    run_dir: Path,
    skill_cache: L1SkillCache,
    evaluator_profile: str,
    max_wall_time_s: float,
) -> dict[str, Any]:
    task = load_task(task_path)
    cache_event = skill_cache.lookup(task, policy=policy)
    skills = list(skill_cache.entries)
    worker_dir = run_dir / "worker_io" / condition_id / f"{task_index:03d}_{task.id}"
    worker_dir.mkdir(parents=True, exist_ok=True)
    input_path = worker_dir / "input.json"
    output_path = worker_dir / "output.json"
    input_path.write_text(
        json.dumps(
            {
                "task_path": str(task_path),
                "policy": policy,
                "max_iters": max_iters,
                "out_dir": str(run_dir / "artifacts" / condition_id),
                "skills": skills,
                "cache_event": cache_event,
                "active_skills_enabled": skill_cache.include_active,
                "evaluator_profile": evaluator_profile,
                "max_wall_time_s": max_wall_time_s,
            },
            ensure_ascii=False,
        )
    )
    start = time.time()
    command = [sys.executable, "-m", "experiments.run_task_worker", str(input_path), str(output_path)]
    try:
        completed = subprocess.run(
            command,
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            timeout=max_wall_time_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _timeout_record(
            task=task,
            condition_id=condition_id,
            task_index=task_index,
            policy=policy,
            evaluator_profile=evaluator_profile,
            skill_cache=skill_cache,
            cache_event=cache_event,
            skills=skills,
            wall_time_s=time.time() - start,
            failure=f"Hard task timeout after {max_wall_time_s}s\nstdout:\n{exc.stdout or ''}\nstderr:\n{exc.stderr or ''}",
        )
    if completed.returncode != 0:
        return _timeout_record(
            task=task,
            condition_id=condition_id,
            task_index=task_index,
            policy=policy,
            evaluator_profile=evaluator_profile,
            skill_cache=skill_cache,
            cache_event=cache_event,
            skills=skills,
            wall_time_s=time.time() - start,
            failure=(
                f"Worker failed with returncode={completed.returncode}\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            ),
            infrastructure_failure=True,
        )
    record = json.loads(output_path.read_text())
    return record


def _timeout_record(
    *,
    task,
    condition_id: str,
    task_index: int,
    policy: str,
    evaluator_profile: str,
    skill_cache: L1SkillCache,
    cache_event: dict[str, Any],
    skills: list[dict[str, Any]],
    wall_time_s: float,
    failure: str,
    infrastructure_failure: bool = False,
) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "source": task.source,
        "family": task.family,
        "tags": task.tags,
        "policy": policy,
        "evaluator_profile": evaluator_profile,
        "active_skills_enabled": skill_cache.include_active,
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
        "passed": False,
        "accepted_by_current_evaluator": False,
        "correctness_claim": "not_proven",
        "evaluator_goal": "find_counterexample_or_bug",
        "evaluator_strength": {
            "lint": False,
            "directed_simulation": False,
            "random_simulation": False,
            "reference_model": False,
            "assertions": False,
            "formal": False,
            "coverage": None,
            "correctness_claim": "not_proven",
        },
        "iterations": 0,
        "max_iters": 0,
        "wall_time_s": round(wall_time_s, 3),
        "timed_out": not infrastructure_failure,
        "infrastructure_failure": infrastructure_failure or True,
        "workdir": str(Path("")),
        "failure_summary_tail": failure[-2000:],
        "candidate_skills_generated": [],
        "condition_id": condition_id,
        "task_index": task_index,
    }


def _condition_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_records(records)
    hits = sum(1 for record in records if not record.get("skill_cache_miss", True))
    misses = sum(1 for record in records if record.get("skill_cache_miss", False))
    generated = sum(len(record.get("candidate_skills_generated", [])) for record in records)
    wall_times = [record["wall_time_s"] for record in records]
    summary.update(
        {
            "l1_hits": hits,
            "l1_misses": misses,
            "l1_hit_rate": round(hits / len(records), 4) if records else 0.0,
            "candidate_skills_generated": generated,
            "mean_wall_time_s": round(sum(wall_times) / len(wall_times), 4) if wall_times else None,
        }
    )
    return summary


@app.command()
def main(
    config: Path = typer.Argument(..., help="Task-set ablation config YAML."),
    dry_run: bool = typer.Option(True, help="Only print the plan."),
    out_dir: Path = typer.Option(Path("results/taskset_ablation"), help="Output directory."),
) -> None:
    data = yaml.safe_load(config.read_text())
    tasks = [Path(path) for path in data.get("tasks", [])]
    conditions = data.get("conditions", [])
    max_iters = int(data.get("max_repair_iters", 2))
    default_capacity = int(data.get("skill_l1_capacity", 6))
    default_profile = data.get("evaluator_profile", "adversarial_v2")
    default_wall_time = data.get("max_task_wall_time_s")
    hard_timeout = bool(data.get("hard_timeout", False))

    table = Table(title="Task-Set Ablation Plan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("config", str(config))
    table.add_row("tasks", str(len(tasks)))
    table.add_row("conditions", ", ".join(condition["id"] for condition in conditions))
    table.add_row("max_iters", str(max_iters))
    table.add_row("hard_timeout", str(hard_timeout))
    table.add_row("dry_run", str(dry_run))
    console.print(table)
    for task_path in tasks:
        task = load_task(task_path)
        console.print(f"- {task.id}: {task.family} difficulty={task.difficulty}")
    if dry_run:
        return

    llm = None if hard_timeout else LLMClient()
    run_name = f"{data.get('name', 'taskset_ablation')}_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = out_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    records_path = run_dir / "records.jsonl"

    records: list[dict[str, Any]] = []
    with records_path.open("w") as f:
        for condition in conditions:
            condition_id = condition["id"]
            policy = condition.get("policy", "locality_aware")
            active_skills = bool(condition.get("active_skills", True))
            evaluator_profile = condition.get("evaluator_profile", default_profile)
            capacity = int(condition.get("skill_l1_capacity", default_capacity))
            max_wall_time_s = condition.get("max_task_wall_time_s", default_wall_time)
            max_wall_time_s = None if max_wall_time_s is None else float(max_wall_time_s)
            skill_cache = L1SkillCache(capacity=capacity, include_active=active_skills)

            for task_index, task_path in enumerate(tasks, start=1):
                task = load_task(task_path)
                console.print(f"running condition={condition_id} task={task_index}/{len(tasks)} id={task.id}")
                if hard_timeout:
                    if max_wall_time_s is None:
                        raise typer.BadParameter("hard_timeout requires max_task_wall_time_s")
                    record = _hard_timeout_record(
                        task_path=task_path,
                        condition_id=condition_id,
                        task_index=task_index,
                        policy=policy,
                        max_iters=max_iters,
                        run_dir=run_dir,
                        skill_cache=skill_cache,
                        evaluator_profile=evaluator_profile,
                        max_wall_time_s=max_wall_time_s,
                    )
                else:
                    assert llm is not None
                    record = run_task_loop(
                        task,
                        policy=policy,
                        max_iters=max_iters,
                        out_dir=run_dir / "artifacts" / condition_id,
                        llm=llm,
                        skill_cache=skill_cache,
                        evaluator_profile=evaluator_profile,
                        max_wall_time_s=max_wall_time_s,
                    )
                record["condition_id"] = condition_id
                record["task_index"] = task_index
                records.append(record)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                console.print(
                    {
                        "condition_id": condition_id,
                        "task_id": record["task_id"],
                        "accepted": record["accepted_by_current_evaluator"],
                        "iterations": record["iterations"],
                        "l1_event": record["skill_cache_event"],
                        "wall_time_s": record["wall_time_s"],
                    }
                )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["condition_id"], []).append(record)
    summary = {condition_id: _condition_summary(condition_records) for condition_id, condition_records in grouped.items()}
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    result_table = Table(title="Task-Set Ablation Summary")
    result_table.add_column("Condition")
    result_table.add_column("Solved")
    result_table.add_column("Pass@k")
    result_table.add_column("ACPS")
    result_table.add_column("L1 Hit")
    result_table.add_column("Candidates")
    result_table.add_column("Timeouts")
    for condition_id, item in summary.items():
        result_table.add_row(
            condition_id,
            f"{item['solved']}/{item['tasks']}",
            str(item["pass_at_k"]),
            str(item["acps_iter"]),
            f"{item['l1_hits']}/{item['tasks']}",
            str(item["candidate_skills_generated"]),
            str(item["timeouts"]),
        )
    console.print(result_table)
    console.print(f"records={records_path}")
    console.print(f"summary={summary_path}")


if __name__ == "__main__":
    app()
