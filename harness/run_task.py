from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agents.llm import LLMClient
from cache.skill_cache import L1SkillCache
from cache.retrieve import retrieve_skills
from harness.runner import run_task_loop
from harness.task_schema import load_task
from harness.tools import check_hdl_tools

app = typer.Typer(help="Run one HDL task through the coder/evaluator loop.")
console = Console()


@app.command()
def main(
    task: Path = typer.Argument(..., help="Path to a task YAML file."),
    policy: str = typer.Option("fixed", help="Skill retrieval/cache policy."),
    dry_run: bool = typer.Option(True, help="Only validate environment and task path."),
    max_iters: int = typer.Option(3, help="Maximum coder/evaluator attempts."),
    out_dir: Path = typer.Option(Path("results/runs"), help="Directory for run artifacts."),
    evaluator_profile: str = typer.Option("adversarial_v2", help="Evaluator profile: basic or adversarial_v2."),
    active_skills: bool = typer.Option(True, help="Load active skills in addition to seed skills."),
) -> None:
    table = Table(title="HDL Agent Task Smoke Check")
    loaded_task = load_task(task) if task.exists() else None
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("task", str(task))
    table.add_row("task_exists", str(task.exists()))
    if loaded_task is not None:
        table.add_row("task_id", loaded_task.id)
        table.add_row("family", loaded_task.family)
        table.add_row("tags", ", ".join(loaded_task.tags))
        table.add_row("language", loaded_task.language)
    table.add_row("policy", policy)
    table.add_row("evaluator_profile", evaluator_profile)
    table.add_row("active_skills", str(active_skills))
    table.add_row("dry_run", str(dry_run))
    for name, path in check_hdl_tools().items():
        table.add_row(name, path or "not found")
    console.print(table)

    if not task.exists():
        raise typer.Exit(code=2)
    if dry_run:
        return

    assert loaded_task is not None
    skills = retrieve_skills(loaded_task, policy=policy, include_active=active_skills)
    console.print(f"retrieved_skills={[skill['id'] for skill in skills]}")

    llm = LLMClient()
    run_dir = out_dir / loaded_task.id
    record = run_task_loop(
        loaded_task,
        policy=policy,
        max_iters=max_iters,
        out_dir=out_dir,
        llm=llm,
        skill_cache=L1SkillCache(include_active=active_skills),
        evaluator_profile=evaluator_profile,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    console.print(record)
    if not record["passed"]:
        console.print(record["failure_summary_tail"])
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
