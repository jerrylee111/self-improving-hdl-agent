from __future__ import annotations

import json
import os
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

app = typer.Typer(help="Batch-validate candidate skill blocks and write an aggregate report.")
console = Console()


def _load_skill(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not data:
        raise RuntimeError(f"empty skill file: {path}")
    return data


def _latest_report(out_dir: Path, candidate_id: str, started_at: float) -> Path | None:
    reports = []
    for path in out_dir.glob(f"{candidate_id}_*/report.json"):
        try:
            if path.stat().st_mtime >= started_at:
                reports.append(path)
        except FileNotFoundError:
            continue
    if not reports:
        return None
    return max(reports, key=lambda path: path.stat().st_mtime)


def _run_one(
    path: Path,
    out_dir: Path,
    validation_dir: Path,
    limit: int,
    max_iters: int,
    capacity: int,
    policy: str,
    max_task_wall_time_s: float,
    command_timeout_s: float,
    promote: bool,
) -> dict[str, Any]:
    skill = _load_skill(path)
    started_at = time.time()
    cmd = [
        sys.executable,
        "scripts/validate_candidate_skill.py",
        str(path),
        "--validation-dir",
        str(validation_dir),
        "--out-dir",
        str(out_dir),
        "--limit",
        str(limit),
        "--max-iters",
        str(max_iters),
        "--capacity",
        str(capacity),
        "--policy",
        policy,
        "--max-task-wall-time-s",
        str(max_task_wall_time_s),
    ]
    if promote:
        cmd.append("--promote")

    try:
        env = dict(os.environ)
        root = str(Path.cwd())
        env["PYTHONPATH"] = root if not env.get("PYTHONPATH") else f"{root}{os.pathsep}{env['PYTHONPATH']}"
        completed = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=command_timeout_s,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "candidate_path": str(path),
            "candidate_id": skill.get("id"),
            "agent": skill.get("agent"),
            "name": skill.get("name"),
            "status": "timeout",
            "returncode": None,
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }

    report_path = _latest_report(out_dir, str(skill.get("id")), started_at)
    if completed.returncode != 0 or report_path is None:
        return {
            "candidate_path": str(path),
            "candidate_id": skill.get("id"),
            "agent": skill.get("agent"),
            "name": skill.get("name"),
            "status": "error",
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }

    report = json.loads(report_path.read_text())
    baseline = report.get("baseline_summary", {})
    candidate = report.get("candidate_summary", {})
    return {
        "candidate_path": str(path),
        "candidate_id": report.get("candidate_id"),
        "agent": report.get("agent"),
        "name": skill.get("name"),
        "status": "ok",
        "decision": report.get("decision"),
        "reason": report.get("reason"),
        "validation_tasks": report.get("validation_tasks", []),
        "baseline_solved": baseline.get("solved"),
        "candidate_solved": candidate.get("solved"),
        "baseline_acps_iter": baseline.get("acps_iter"),
        "candidate_acps_iter": candidate.get("acps_iter"),
        "baseline_timeouts": baseline.get("timeouts"),
        "candidate_timeouts": candidate.get("timeouts"),
        "report_path": str(report_path),
    }


def _markdown(rows: list[dict[str, Any]], run_dir: Path, title: str) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("decision") or row.get("status"))
        counts[key] = counts.get(key, 0) + 1

    lines = [
        f"# {title}",
        "",
        "## 汇总",
        "",
        f"- block 数量：{len(rows)}",
        f"- 决策统计：{json.dumps(counts, ensure_ascii=False, sort_keys=True)}",
        "",
        "## 明细",
        "",
        "| block | agent | decision | baseline solved | candidate solved | baseline ACPS | candidate ACPS |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        name = row.get("name") or row.get("candidate_id") or Path(row["candidate_path"]).name
        lines.append(
            "| {name} | {agent} | {decision} | {bs} | {cs} | {ba} | {ca} |".format(
                name=name,
                agent=row.get("agent", ""),
                decision=row.get("decision") or row.get("status", ""),
                bs=row.get("baseline_solved", ""),
                cs=row.get("candidate_solved", ""),
                ba=row.get("baseline_acps_iter", ""),
                ca=row.get("candidate_acps_iter", ""),
            )
        )
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- `promote`：validation split 上通过任务数更多，或通过数相同但 ACPS-Iter 严格降低。",
            "- `keep_candidate`：没有退化，但也没有严格提升，暂不进入 active。",
            "- `reject`：validation split 上相对 baseline 退化。",
            "- evaluator block 目前通常为 `pending`，因为 evaluator skill 尚未真正接入 adversarial test generation。",
            "",
            f"原始聚合结果：`{run_dir / 'aggregate.json'}`",
        ]
    )
    return "\n".join(lines) + "\n"


@app.command()
def main(
    candidate_dir: Path = typer.Option(Path("skills/candidate_blocks"), help="Candidate block directory."),
    validation_dir: Path = typer.Option(
        Path("benchmarks/tasks/external/verilogeval/validation"),
        help="Validation task directory.",
    ),
    out_dir: Path = typer.Option(Path("results/candidate_validation"), help="Validation output root."),
    agent: str = typer.Option("coder", help="Filter by agent: coder, evaluator, or all."),
    limit: int = typer.Option(1, help="Maximum matching validation tasks per block."),
    max_blocks: int | None = typer.Option(None, help="Optional cap on number of blocks."),
    max_iters: int = typer.Option(2, help="Max repair iterations per task."),
    capacity: int = typer.Option(6, help="L1 skill cache capacity."),
    policy: str = typer.Option("locality_aware", help="Skill retrieval policy."),
    max_task_wall_time_s: float = typer.Option(120.0, help="Cooperative per-task wall-time budget."),
    command_timeout_s: float = typer.Option(360.0, help="Subprocess timeout per block."),
    promote: bool = typer.Option(False, help="Promote blocks whose decision is promote."),
) -> None:
    run_id = time.strftime("block_validation_%Y%m%d_%H%M%S")
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(candidate_dir.glob("candidate_block.*.yaml"))
    if agent != "all":
        paths = [path for path in paths if _load_skill(path).get("agent") == agent]
    if max_blocks is not None:
        paths = paths[:max_blocks]
    if not paths:
        raise typer.Exit(code=3)

    rows = []
    for idx, path in enumerate(paths, start=1):
        console.print(f"[{idx}/{len(paths)}] validating {path.name}")
        rows.append(
            _run_one(
                path=path,
                out_dir=out_dir,
                validation_dir=validation_dir,
                limit=limit,
                max_iters=max_iters,
                capacity=capacity,
                policy=policy,
                max_task_wall_time_s=max_task_wall_time_s,
                command_timeout_s=command_timeout_s,
                promote=promote,
            )
        )

    aggregate = {
        "run_id": run_id,
        "agent": agent,
        "candidate_dir": str(candidate_dir),
        "validation_dir": str(validation_dir),
        "limit": limit,
        "max_iters": max_iters,
        "capacity": capacity,
        "policy": policy,
        "max_task_wall_time_s": max_task_wall_time_s,
        "command_timeout_s": command_timeout_s,
        "promote": promote,
        "rows": rows,
    }
    aggregate_path = run_dir / "aggregate.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2, ensure_ascii=False))
    markdown_path = run_dir / "summary.md"
    markdown_path.write_text(_markdown(rows, run_dir, "Candidate Block 批量验证"), encoding="utf-8")

    table = Table(title="Candidate Block Batch Validation")
    table.add_column("Decision")
    table.add_column("Count", justify="right")
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("decision") or row.get("status"))
        counts[key] = counts.get(key, 0) + 1
    for key, count in sorted(counts.items()):
        table.add_row(key, str(count))
    console.print(table)
    console.print(f"aggregate={aggregate_path}")
    console.print(f"summary={markdown_path}")


if __name__ == "__main__":
    app()
