from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness.task_schema import HDLTask
from harness.testbench import generate_testbench
from harness.tools import ToolResult, run_command


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    results: list[ToolResult]
    workdir: Path

    @property
    def summary(self) -> str:
        chunks = []
        for result in self.results:
            chunks.append(
                f"$ {' '.join(result.command)}\n"
                f"returncode={result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return "\n\n".join(chunks)


def evaluate_rtl(task: HDLTask, rtl: str, workdir: Path) -> EvaluationResult:
    workdir.mkdir(parents=True, exist_ok=True)
    design_path = workdir / ("design.sv" if task.language == "systemverilog" else "design.v")
    tb_path = workdir / "tb.sv"
    design_path.write_text(rtl)
    tb_path.write_text(generate_testbench(task))

    results: list[ToolResult] = []
    results.append(
        run_command(["verilator", "--lint-only", "-Wall", "--Wno-fatal", design_path.name], cwd=workdir)
    )
    if not results[-1].ok:
        return EvaluationResult(False, results, workdir)

    sim_out = workdir / "sim.out"
    results.append(
        run_command(
            ["iverilog", "-g2012", "-o", sim_out.name, tb_path.name, design_path.name],
            cwd=workdir,
        )
    )
    if not results[-1].ok:
        return EvaluationResult(False, results, workdir)

    results.append(run_command(["vvp", sim_out.name], cwd=workdir))
    return EvaluationResult(results[-1].ok and "PASS" in results[-1].stdout, results, workdir)
