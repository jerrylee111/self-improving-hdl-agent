from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from harness.task_schema import load_task
from harness.testbench import generate_testbench
from harness.tools import run_command

app = typer.Typer(help="Evaluate HDL mutants against basic and adversarial evaluators.")
console = Console()


def basic_round_robin_tb() -> str:
    return """`timescale 1ns/1ps
module tb;
  reg clk=0, reset=0; reg [1:0] req=0; wire [1:0] grant;
  top_module dut(.clk(clk), .reset(reset), .req(req), .grant(grant));
  always #1 clk = ~clk;
  task step(input [1:0] r, input [1:0] exp);
    begin
      req=r; @(posedge clk); #0.1;
      if (grant !== exp) $fatal(1, "grant mismatch");
    end
  endtask
  initial begin
    reset=1; step(2'b00,2'b00); reset=0;
    step(2'b01,2'b01);
    step(2'b10,2'b10);
    step(2'b11,2'b01);
    step(2'b11,2'b10);
    step(2'b11,2'b01);
    step(2'b00,2'b00);
    step(2'b11,2'b10);
    $display("PASS"); $finish;
  end
endmodule
"""


def evaluator_profiles(task_path: Path) -> dict[str, str]:
    task = load_task(task_path)
    return {
        "basic": basic_round_robin_tb(),
        "adversarial_v2": generate_testbench(task),
    }


def evaluate_design(design: Path, tb: str, workdir: Path) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    design_path = workdir / "design.v"
    tb_path = workdir / "tb.sv"
    sim_path = workdir / "sim.out"
    design_path.write_text(design.read_text())
    tb_path.write_text(tb)

    results = [
        run_command(["verilator", "--lint-only", "-Wall", "--Wno-fatal", design_path.name], cwd=workdir),
    ]
    if results[-1].ok:
        results.append(
            run_command(["iverilog", "-g2012", "-o", sim_path.name, tb_path.name, design_path.name], cwd=workdir)
        )
    if results[-1].ok:
        results.append(run_command(["vvp", sim_path.name], cwd=workdir))

    accepted = bool(results[-1].ok and "PASS" in results[-1].stdout)
    failure_tail = ""
    if not accepted:
        chunks = []
        for result in results:
            chunks.append(
                f"$ {' '.join(result.command)}\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        failure_tail = "\n\n".join(chunks)[-2000:]
    return {
        "accepted": accepted,
        "commands": [
            {
                "tool": result.tool,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-500:],
                "stderr_tail": result.stderr[-500:],
            }
            for result in results
        ],
        "failure_tail": failure_tail,
    }


def summarize_profile(profile: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    mutants = [record for record in records if record["kind"] == "mutant"]
    killed = [record for record in mutants if not record["accepted"]]
    survived = [record for record in mutants if record["accepted"]]
    correct = [record for record in records if record["kind"] == "correct"]
    correct_accepted = all(record["accepted"] for record in correct)
    return {
        "profile": profile,
        "mutants": len(mutants),
        "killed": len(killed),
        "survived": len(survived),
        "mutant_kill_rate": round(len(killed) / len(mutants), 4) if mutants else 0.0,
        "correct_designs": len(correct),
        "correct_accepted": correct_accepted,
        "killed_ids": [record["id"] for record in killed],
        "survived_ids": [record["id"] for record in survived],
    }


@app.command()
def main(
    mutants_dir: Path = typer.Option(
        Path("benchmarks/mutants/round_robin_arbiter2"),
        help="Directory containing correct_*.v and bug_*.v designs.",
    ),
    task: Path = typer.Option(
        Path("benchmarks/tasks/local_seed/round_robin_arbiter2.yaml"),
        help="Task YAML used for adversarial evaluator generation.",
    ),
    out_dir: Path = typer.Option(Path("results/mutant_eval"), help="Output directory."),
) -> None:
    profiles = evaluator_profiles(task)
    designs = sorted(mutants_dir.glob("*.v"))
    if not designs:
        raise typer.Exit(code=2)

    run_dir = out_dir / "round_robin_arbiter2"
    records: list[dict[str, Any]] = []
    for profile, tb in profiles.items():
        for design in designs:
            design_id = design.stem
            kind = "correct" if design_id.startswith("correct") else "mutant"
            result = evaluate_design(design, tb, run_dir / profile / design_id)
            records.append(
                {
                    "profile": profile,
                    "id": design_id,
                    "kind": kind,
                    **result,
                }
            )

    summaries = [summarize_profile(profile, [r for r in records if r["profile"] == profile]) for profile in profiles]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "records.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")
    (run_dir / "summary.json").write_text(json.dumps({"summaries": summaries}, indent=2, ensure_ascii=False))

    table = Table(title="Round-Robin Arbiter Mutant Evaluation")
    table.add_column("Profile")
    table.add_column("Mutants")
    table.add_column("Killed")
    table.add_column("Survived")
    table.add_column("Kill Rate")
    table.add_column("Correct Accepted")
    for summary in summaries:
        table.add_row(
            summary["profile"],
            str(summary["mutants"]),
            str(summary["killed"]),
            str(summary["survived"]),
            f"{summary['mutant_kill_rate']:.4f}",
            str(summary["correct_accepted"]),
        )
    console.print(table)
    console.print(f"records={run_dir / 'records.jsonl'}")
    console.print(f"summary={run_dir / 'summary.json'}")


if __name__ == "__main__":
    app()
