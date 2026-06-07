from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import typer
from rich.console import Console
from rich.table import Table
import yaml

from agents.llm import LLMClient
from cache.skill_cache import L1SkillCache
from harness.runner import run_task_loop, summarize_records
from harness.task_schema import load_task

app = typer.Typer(help="Run HDL agent experiments.")
console = Console()


@app.command()
def main(
    config: Path = typer.Argument(..., help="Path to an experiment config YAML file."),
    dry_run: bool = typer.Option(True, help="Only validate config path."),
    out_dir: Path = typer.Option(Path("results/experiments"), help="Experiment output directory."),
) -> None:
    if not config.exists():
        raise typer.Exit(code=2)
    data = yaml.safe_load(config.read_text())
    tasks = [Path(path) for path in data.get("tasks", [])]
    policies = data.get("policies", ["fixed"])
    max_iters = int(data.get("max_repair_iters", 3))
    evaluator_profile = data.get("evaluator_profile", "adversarial_v2")
    active_skills = bool(data.get("active_skills", True))
    max_wall_time_s = data.get("max_task_wall_time_s")
    max_wall_time_s = None if max_wall_time_s is None else float(max_wall_time_s)

    table = Table(title="Experiment Plan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("config", str(config))
    table.add_row("tasks", str(len(tasks)))
    table.add_row("policies", ", ".join(policies))
    table.add_row("evaluator_profile", evaluator_profile)
    table.add_row("active_skills", str(active_skills))
    table.add_row("max_iters", str(max_iters))
    table.add_row("max_task_wall_time_s", str(max_wall_time_s))
    table.add_row("dry_run", str(dry_run))
    console.print(table)
    for task_path in tasks:
        task = load_task(task_path)
        console.print(f"- {task.id}: {task.family} [{', '.join(task.tags)}]")
    if dry_run:
        return

    llm = LLMClient()
    run_name = f"{data.get('name', 'experiment')}_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = out_dir / run_name
    records_path = run_dir / "records.jsonl"
    summary_path = run_dir / "summary.json"
    run_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    with records_path.open("w") as f:
        for policy in policies:
            skill_cache = L1SkillCache(
                capacity=int(data.get("skill_l1_capacity", 6)),
                include_active=active_skills,
            )
            for task_path in tasks:
                task = load_task(task_path)
                console.print(f"running task={task.id} policy={policy}")
                record = run_task_loop(
                    task,
                    policy=policy,
                    max_iters=max_iters,
                    out_dir=run_dir / "artifacts" / policy,
                    llm=llm,
                    skill_cache=skill_cache,
                    evaluator_profile=evaluator_profile,
                    max_wall_time_s=max_wall_time_s,
                )
                records.append(record)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                console.print(
                    {
                        "task_id": record["task_id"],
                        "passed": record["passed"],
                        "accepted_by_current_evaluator": record["accepted_by_current_evaluator"],
                        "iterations": record["iterations"],
                        "wall_time_s": record["wall_time_s"],
                    }
                )

    summary = summarize_records(records)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    console.print(summary)
    console.print(f"records={records_path}")
    console.print(f"summary={summary_path}")


if __name__ == "__main__":
    app()
