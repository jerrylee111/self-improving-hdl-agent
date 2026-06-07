from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from agents.llm import LLMClient
from cache.skill_cache import L1SkillCache
from harness.runner import run_task_loop
from harness.task_schema import load_task

app = typer.Typer(help="Run repeated task-level ablations with explicit cache/evaluator conditions.")
console = Console()


def summarize_condition(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [r for r in records if r["accepted_by_current_evaluator"]]
    api_failures = [
        r
        for r in records
        if (not r["accepted_by_current_evaluator"]) and "LLM call failed" in r.get("failure_summary_tail", "")
    ]
    timeouts = [r for r in records if r.get("timed_out")]
    effective_records = [r for r in records if r not in api_failures]
    effective_accepted = [r for r in effective_records if r["accepted_by_current_evaluator"]]
    iterations = [r["iterations"] for r in accepted]
    wall_times = [r["wall_time_s"] for r in records]
    return {
        "runs": len(records),
        "accepted": len(accepted),
        "accepted_rate": round(len(accepted) / len(records), 4) if records else 0.0,
        "api_failures": len(api_failures),
        "timeouts": len(timeouts),
        "effective_runs": len(effective_records),
        "effective_accepted": len(effective_accepted),
        "effective_accepted_rate": round(len(effective_accepted) / len(effective_records), 4)
        if effective_records
        else None,
        "mean_iterations_to_acceptance": round(sum(iterations) / len(iterations), 4) if iterations else None,
        "mean_wall_time_s": round(sum(wall_times) / len(wall_times), 4) if wall_times else None,
        "retrieved_skill_sets": sorted({tuple(r["retrieved_skills"]) for r in records}),
    }


@app.command()
def main(
    config: Path = typer.Argument(..., help="Repeated ablation config YAML."),
    repeats: int = typer.Option(5, help="Number of repeats per condition."),
    out_dir: Path = typer.Option(Path("results/repeated_ablation"), help="Output directory."),
) -> None:
    data = yaml.safe_load(config.read_text())
    conditions = data.get("conditions", [])
    run_name = f"{data.get('name', 'repeated_ablation')}_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = out_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    llm = LLMClient()
    records: list[dict[str, Any]] = []
    records_path = run_dir / "records.jsonl"
    with records_path.open("w") as f:
        for condition in conditions:
            condition_id = condition["id"]
            task = load_task(Path(condition["task"]))
            policy = condition.get("policy", "tag_topk")
            active_skills = bool(condition.get("active_skills", True))
            evaluator_profile = condition.get("evaluator_profile", "adversarial_v2")
            max_iters = int(condition.get("max_iters", data.get("max_repair_iters", 3)))
            capacity = int(condition.get("skill_l1_capacity", data.get("skill_l1_capacity", 6)))
            max_wall_time_s = condition.get("max_task_wall_time_s", data.get("max_task_wall_time_s"))
            max_wall_time_s = None if max_wall_time_s is None else float(max_wall_time_s)
            for repeat in range(1, repeats + 1):
                console.print(f"running condition={condition_id} repeat={repeat}/{repeats}")
                record = run_task_loop(
                    task,
                    policy=policy,
                    max_iters=max_iters,
                    out_dir=run_dir / "artifacts" / condition_id / f"repeat_{repeat}",
                    llm=llm,
                    skill_cache=L1SkillCache(capacity=capacity, include_active=active_skills),
                    evaluator_profile=evaluator_profile,
                    max_wall_time_s=max_wall_time_s,
                )
                record["condition_id"] = condition_id
                record["repeat"] = repeat
                records.append(record)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                console.print(
                    {
                        "condition_id": condition_id,
                        "repeat": repeat,
                        "accepted": record["accepted_by_current_evaluator"],
                        "iterations": record["iterations"],
                        "wall_time_s": record["wall_time_s"],
                    }
                )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["condition_id"]].append(record)
    summary = {
        condition_id: summarize_condition(condition_records)
        for condition_id, condition_records in grouped.items()
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    table = Table(title="Repeated Task Ablation")
    table.add_column("Condition")
    table.add_column("Accepted")
    table.add_column("Rate")
    table.add_column("Mean Iter")
    table.add_column("Mean Wall")
    table.add_column("API Fail")
    table.add_column("Timeouts")
    table.add_column("Effective")
    for condition_id, item in summary.items():
        table.add_row(
            condition_id,
            f"{item['accepted']}/{item['runs']}",
            f"{item['accepted_rate']:.4f}",
            str(item["mean_iterations_to_acceptance"]),
            str(item["mean_wall_time_s"]),
            str(item["api_failures"]),
            str(item["timeouts"]),
            f"{item['effective_accepted']}/{item['effective_runs']}",
        )
    console.print(table)
    console.print(f"records={records_path}")
    console.print(f"summary={run_dir / 'summary.json'}")


if __name__ == "__main__":
    app()
