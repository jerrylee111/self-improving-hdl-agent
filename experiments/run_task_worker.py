from __future__ import annotations

import json
from pathlib import Path

import typer

from agents.llm import LLMClient
from harness.runner import run_task_loop_with_context
from harness.task_schema import load_task

app = typer.Typer(help="Worker process for one hard-timeout task run.")


@app.command()
def main(input_json: Path, output_json: Path) -> None:
    payload = json.loads(input_json.read_text())
    task = load_task(Path(payload["task_path"]))
    llm = LLMClient()
    record = run_task_loop_with_context(
        task,
        policy=payload["policy"],
        max_iters=int(payload["max_iters"]),
        out_dir=Path(payload["out_dir"]),
        llm=llm,
        skills=payload["skills"],
        cache_event=payload["cache_event"],
        active_skills_enabled=bool(payload["active_skills_enabled"]),
        evaluator_profile=payload["evaluator_profile"],
        max_wall_time_s=payload.get("max_wall_time_s"),
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
