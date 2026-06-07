from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Build a hard task-set config from prior taskset records.")
console = Console()


def _resolve_task_path(task_id: str, task_root: Path) -> str | None:
    matches = sorted(task_root.glob(f"**/{task_id}.yaml"))
    if not matches:
        return None
    return str(matches[0])


def _score_record(record: dict[str, Any]) -> float:
    score = 0.0
    if record.get("infrastructure_failure"):
        score += 1.0
    if record.get("timed_out"):
        score += 2.0
    if not record.get("passed"):
        score += 4.0
    iterations = int(record.get("iterations") or 0)
    if iterations > 1:
        score += float(iterations - 1)
    candidates = record.get("candidate_skills_generated") or []
    score += min(len(candidates), 4) * 0.25
    wall_time = float(record.get("wall_time_s") or 0.0)
    score += min(wall_time / 120.0, 2.0)
    return round(score, 4)


def _load_records(paths: list[Path], conditions: set[str] | None) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "task_id": None,
            "source": None,
            "family": None,
            "tags": [],
            "score": 0.0,
            "evidence": [],
        }
    )
    for path in paths:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            condition = record.get("condition_id")
            if conditions and condition not in conditions:
                continue
            task_id = record["task_id"]
            row = grouped[task_id]
            row["task_id"] = task_id
            row["source"] = record.get("source")
            row["family"] = record.get("family")
            row["tags"] = record.get("tags", [])
            score = _score_record(record)
            row["score"] += score
            row["evidence"].append(
                {
                    "condition_id": condition,
                    "passed": record.get("passed"),
                    "iterations": record.get("iterations"),
                    "timed_out": record.get("timed_out", False),
                    "infrastructure_failure": record.get("infrastructure_failure", False),
                    "wall_time_s": record.get("wall_time_s"),
                    "candidate_count": len(record.get("candidate_skills_generated") or []),
                    "score": score,
                }
            )
    return grouped


@app.command()
def main(
    records: list[Path] = typer.Argument(..., help="One or more taskset records.jsonl files."),
    out_config: Path = typer.Option(
        Path("experiments/configs/hard_task_subset_from_records.yaml"),
        help="Output taskset config path.",
    ),
    out_manifest: Path | None = typer.Option(None, help="Optional difficulty manifest JSON path."),
    conditions: str = typer.Option(
        "",
        help="Comma-separated condition ids to score. Empty means all conditions.",
    ),
    top_k: int = typer.Option(8, help="Number of hard tasks to keep."),
    include_timeouts: bool = typer.Option(False, help="Include infrastructure timeout tasks."),
    name: str = typer.Option("hard_task_subset_from_records", help="Taskset config name."),
    task_root: Path = typer.Option(Path("benchmarks/tasks"), help="Root used to resolve task IDs."),
) -> None:
    condition_set = {item.strip() for item in conditions.split(",") if item.strip()} or None
    rows = _load_records(records, condition_set)
    selected = []
    for row in rows.values():
        if not include_timeouts and any(item.get("infrastructure_failure") for item in row["evidence"]):
            continue
        task_path = _resolve_task_path(str(row["task_id"]), task_root)
        if not task_path:
            continue
        row["task_path"] = task_path
        selected.append(row)
    selected.sort(key=lambda item: (-item["score"], str(item["task_id"])))
    selected = selected[:top_k]

    config = {
        "name": name,
        "max_repair_iters": 2,
        "skill_l1_capacity": 6,
        "max_task_wall_time_s": 240,
        "hard_timeout": True,
        "evaluator_profile": "adversarial_v2",
        "conditions": [
            {"id": f"{name}_no_skill", "active_skills": False, "policy": "no_skill"},
            {"id": f"{name}_seed_only", "active_skills": False, "policy": "locality_aware"},
            {"id": f"{name}_active", "active_skills": True, "policy": "locality_aware"},
        ],
        "tasks": [row["task_path"] for row in selected],
    }
    out_config.parent.mkdir(parents=True, exist_ok=True)
    out_config.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))

    manifest = {
        "records": [str(path) for path in records],
        "conditions": sorted(condition_set) if condition_set else "all",
        "include_timeouts": include_timeouts,
        "top_k": top_k,
        "selected": selected,
    }
    if out_manifest is None:
        out_manifest = out_config.with_suffix(".manifest.json")
    out_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    table = Table(title="Hard Task Subset")
    table.add_column("Task")
    table.add_column("Score", justify="right")
    table.add_column("Family")
    table.add_column("Source")
    for row in selected:
        table.add_row(
            str(row["task_id"]),
            f"{row['score']:.2f}",
            str(row.get("family")),
            str(row.get("task_path")),
        )
    console.print(table)
    console.print(f"config={out_config}")
    console.print(f"manifest={out_manifest}")


if __name__ == "__main__":
    app()
