from __future__ import annotations

import json
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agents.coder import generate_rtl
from agents.llm import LLMClient
from cache.retrieve import retrieve_skills
from harness.evaluate import evaluate_rtl
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
    table.add_row("dry_run", str(dry_run))
    for name, path in check_hdl_tools().items():
        table.add_row(name, path or "not found")
    console.print(table)

    if not task.exists():
        raise typer.Exit(code=2)
    if dry_run:
        return

    assert loaded_task is not None
    skills = retrieve_skills(loaded_task)
    console.print(f"retrieved_skills={[skill['id'] for skill in skills]}")

    llm = LLMClient()
    run_dir = out_dir / loaded_task.id
    start = time.time()
    previous_rtl: str | None = None
    feedback: str | None = None
    final_result = None

    for attempt in range(1, max_iters + 1):
        console.print(f"attempt={attempt}")
        rtl = generate_rtl(loaded_task, skills, llm, previous_rtl=previous_rtl, feedback=feedback)
        attempt_dir = run_dir / f"attempt_{attempt}"
        result = evaluate_rtl(loaded_task, rtl, attempt_dir)
        final_result = result
        console.print({"attempt": attempt, "passed": result.passed, "workdir": str(result.workdir)})
        if result.passed:
            break
        previous_rtl = rtl
        feedback = result.summary[-6000:]

    assert final_result is not None
    record = {
        "task_id": loaded_task.id,
        "source": loaded_task.source,
        "family": loaded_task.family,
        "tags": loaded_task.tags,
        "policy": policy,
        "retrieved_skills": [skill["id"] for skill in skills],
        "passed": final_result.passed,
        "iterations": attempt,
        "max_iters": max_iters,
        "wall_time_s": round(time.time() - start, 3),
        "workdir": str(run_dir),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    console.print(record)
    if not final_result.passed:
        console.print(final_result.summary)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
