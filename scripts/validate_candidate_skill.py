from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from agents.llm import LLMClient
from cache.retrieve import retrieve_skills
from cache.skill_cache import L1SkillCache
from harness.runner import run_task_loop, summarize_records
from harness.task_schema import HDLTask, load_task

app = typer.Typer(help="Validate candidate skills before promoting them into skills/active.")
console = Console()
VALIDATION_RULE_VERSION = "strict_improvement_v1"


def load_candidate(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not data:
        raise RuntimeError(f"empty candidate file: {path}")
    if data.get("version", {}).get("status") not in {"candidate", "candidate_block"}:
        raise RuntimeError(f"not a candidate skill or candidate block: {path}")
    return data


def matching_tasks(candidate: dict[str, Any], validation_dir: Path, limit: int) -> list[Path]:
    patterns = {str(item).lower() for item in candidate.get("task_patterns", [])}
    topics = {str(item).lower() for item in candidate.get("domain", {}).get("topic", [])}
    scored: list[tuple[int, Path]] = []
    for task_path in sorted(validation_dir.glob("*.yaml")):
        task = load_task(task_path)
        task_terms = {task.family.lower(), *[tag.lower() for tag in task.tags]}
        score = len((patterns | topics) & task_terms)
        if score:
            scored.append((score, task_path))
    scored.sort(key=lambda item: (-item[0], str(item[1])))
    return [path for _, path in scored[:limit]]


def _prefilled_cache(task: HDLTask, candidate: dict[str, Any], policy: str, capacity: int) -> L1SkillCache:
    base_skills = retrieve_skills(task, policy=policy, budget=max(1, capacity - 1), agent="coder", include_active=False)
    entries = [*base_skills, candidate][:capacity]
    return L1SkillCache(capacity=capacity, agent="coder", include_active=False, entries=entries)


def _candidate_active_copy(candidate: dict[str, Any]) -> dict[str, Any]:
    promoted = dict(candidate)
    promoted["id"] = candidate["id"].replace("candidate_block.", "skill.", 1).replace("candidate.", "skill.", 1)
    promoted["version"] = dict(candidate.get("version", {}))
    promoted["version"]["status"] = "active"
    promoted["validation"] = dict(candidate.get("validation", {}))
    return promoted


def promote_candidate(candidate_path: Path, active_dir: Path, report: dict[str, Any]) -> Path:
    candidate = load_candidate(candidate_path)
    promoted = _candidate_active_copy(candidate)
    promoted.setdefault("validation", {})
    promoted["validation"].setdefault("promotion", [])
    promoted["validation"]["promotion"].append(
        {
            "decision": report["decision"],
            "reason": report["reason"],
            "report_path": report["report_path"],
            "timestamp": int(time.time()),
        }
    )
    active_dir.mkdir(parents=True, exist_ok=True)
    active_path = active_dir / f"{promoted['id']}.yaml"
    active_path.write_text(yaml.safe_dump(promoted, sort_keys=False, allow_unicode=True))
    return active_path


def validation_decision(candidate: dict[str, Any], baseline: dict[str, Any], treatment: dict[str, Any]) -> tuple[str, str]:
    if candidate.get("agent") != "coder":
        return (
            "pending",
            "当前 evaluator skill 还没有接入测试生成器，不能用代码通过率验证；先保留为 pending。",
        )
    if treatment["solved"] > baseline["solved"]:
        return "promote", "candidate condition solved more validation tasks than seed-only baseline"
    if treatment["solved"] == baseline["solved"]:
        base_iter = baseline.get("acps_iter")
        cand_iter = treatment.get("acps_iter")
        if cand_iter is not None and base_iter is not None and cand_iter < base_iter:
            return "promote", "candidate condition kept solved count and strictly reduced ACPS-Iter"
        if cand_iter is not None and (base_iter is None or cand_iter <= base_iter):
            return "keep_candidate", "candidate condition did not regress, but no strict validation improvement was observed"
    return "reject", "candidate condition did not improve validation solved count or ACPS-Iter"


@app.command()
def main(
    candidate_path: Path = typer.Argument(..., help="Candidate skill YAML path."),
    validation_dir: Path = typer.Option(
        Path("benchmarks/tasks/external/verilogeval/validation"),
        help="Validation task directory.",
    ),
    out_dir: Path = typer.Option(Path("results/candidate_validation"), help="Validation result root."),
    active_dir: Path = typer.Option(Path("skills/active"), help="Active skill output directory."),
    limit: int = typer.Option(2, help="Maximum matching validation tasks."),
    policy: str = typer.Option("locality_aware", help="Skill retrieval policy."),
    max_iters: int = typer.Option(2, help="Max repair iterations per task."),
    capacity: int = typer.Option(6, help="L1 skill cache capacity."),
    max_task_wall_time_s: float | None = typer.Option(180.0, help="Cooperative per-task wall-time budget."),
    promote: bool = typer.Option(False, help="Promote when validation decision is promote."),
) -> None:
    candidate = load_candidate(candidate_path)
    task_paths = matching_tasks(candidate, validation_dir, limit)
    if not task_paths:
        raise typer.Exit(code=3)

    run_id = f"{candidate['id']}_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.json"

    if candidate.get("agent") != "coder":
        decision, reason = validation_decision(candidate, summarize_records([]), summarize_records([]))
        report = {
            "candidate_path": str(candidate_path),
            "candidate_id": candidate["id"],
            "agent": candidate.get("agent"),
            "validation_tasks": [str(path) for path in task_paths],
            "baseline_summary": summarize_records([]),
            "candidate_summary": summarize_records([]),
            "baseline_records": [],
            "candidate_records": [],
            "decision": decision,
            "reason": reason,
            "validation_rule_version": VALIDATION_RULE_VERSION,
            "report_path": str(report_path),
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        table = Table(title="Candidate Validation")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("candidate", candidate["id"])
        table.add_row("agent", str(candidate.get("agent")))
        table.add_row("tasks", str(len(task_paths)))
        table.add_row("decision", decision)
        table.add_row("reason", reason)
        table.add_row("report", str(report_path))
        console.print(table)
        return

    llm = LLMClient()

    baseline_records = []
    treatment_records = []
    for task_path in task_paths:
        task = load_task(task_path)
        baseline_records.append(
            run_task_loop(
                task,
                policy=policy,
                max_iters=max_iters,
                out_dir=run_dir / "baseline",
                llm=llm,
                skill_cache=L1SkillCache(capacity=capacity, include_active=False),
                evaluator_profile="adversarial_v2",
                max_wall_time_s=max_task_wall_time_s,
            )
        )
        treatment_records.append(
            run_task_loop(
                task,
                policy=policy,
                max_iters=max_iters,
                out_dir=run_dir / "candidate",
                llm=llm,
                skill_cache=_prefilled_cache(task, candidate, policy, capacity),
                evaluator_profile="adversarial_v2",
                max_wall_time_s=max_task_wall_time_s,
            )
        )

    baseline_summary = summarize_records(baseline_records)
    treatment_summary = summarize_records(treatment_records)
    decision, reason = validation_decision(candidate, baseline_summary, treatment_summary)

    report_path = run_dir / "report.json"
    report = {
        "candidate_path": str(candidate_path),
        "candidate_id": candidate["id"],
        "agent": candidate.get("agent"),
        "validation_tasks": [str(path) for path in task_paths],
        "baseline_summary": baseline_summary,
        "candidate_summary": treatment_summary,
        "baseline_records": baseline_records,
        "candidate_records": treatment_records,
        "decision": decision,
        "reason": reason,
        "validation_rule_version": VALIDATION_RULE_VERSION,
        "report_path": str(report_path),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    active_path = None
    if promote and decision == "promote":
        active_path = promote_candidate(candidate_path, active_dir, report)
    elif decision == "reject":
        rejected_dir = Path("skills/rejected")
        rejected_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate_path, rejected_dir / candidate_path.name)

    table = Table(title="Candidate Validation")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("candidate", candidate["id"])
    table.add_row("agent", str(candidate.get("agent")))
    table.add_row("tasks", str(len(task_paths)))
    table.add_row("baseline", json.dumps(baseline_summary, ensure_ascii=False))
    table.add_row("candidate", json.dumps(treatment_summary, ensure_ascii=False))
    table.add_row("decision", decision)
    table.add_row("reason", reason)
    table.add_row("report", str(report_path))
    if active_path:
        table.add_row("active_path", str(active_path))
    console.print(table)


if __name__ == "__main__":
    app()
