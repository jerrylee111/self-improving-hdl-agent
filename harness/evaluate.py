from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from harness.task_schema import HDLTask
from harness.testbench import generate_basic_testbench, generate_testbench
from harness.tools import ToolResult, run_command


def _prepare_external_testbench(source: str) -> str:
    lines = []
    for line in source.splitlines():
        if "$dumpfile" in line or "$dumpvars" in line:
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    results: list[ToolResult]
    workdir: Path
    strength: dict[str, bool | str | None]

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


def _evaluator_strength(task: HDLTask, profile: str) -> dict[str, bool | str | None]:
    has_adversarial_tb = profile == "adversarial_v2" and task.family == "sequential_arbiter"
    return {
        "profile": profile,
        "lint": bool(task.evaluation.lint),
        "directed_simulation": bool(task.evaluation.simulation),
        "random_simulation": has_adversarial_tb,
        "reference_model": task.expected.type in {"truth_table", "reference_model"},
        "assertions": has_adversarial_tb,
        "formal": bool(task.evaluation.formal),
        "coverage": None,
        "correctness_claim": "not_proven",
    }


def evaluate_rtl(
    task: HDLTask,
    rtl: str,
    workdir: Path,
    evaluator_profile: str = "adversarial_v2",
) -> EvaluationResult:
    if evaluator_profile not in {"basic", "adversarial_v2"}:
        raise ValueError(f"Unknown evaluator profile: {evaluator_profile}")
    workdir.mkdir(parents=True, exist_ok=True)
    design_path = workdir / ("design.sv" if task.language == "systemverilog" else "design.v")
    tb_path = workdir / "tb.sv"
    design_path.write_text(rtl)
    external_testbench = Path(task.evaluation.testbench_file) if task.evaluation.testbench_file else None
    if external_testbench:
        tb_path.write_text(_prepare_external_testbench(external_testbench.read_text()))
    else:
        testbench = generate_basic_testbench(task) if evaluator_profile == "basic" else generate_testbench(task)
        tb_path.write_text(testbench)
    strength = _evaluator_strength(task, evaluator_profile)

    results: list[ToolResult] = []
    results.append(
        run_command(["verilator", "--lint-only", "-Wall", "--Wno-fatal", design_path.name], cwd=workdir)
    )
    if not results[-1].ok:
        return EvaluationResult(False, results, workdir, strength)

    sim_out = workdir / "sim.out"
    compile_inputs = [tb_path.name, design_path.name]
    if task.expected.file:
        ref_path = Path(task.expected.file)
        local_ref_path = workdir / ref_path.name
        local_ref_path.write_text(ref_path.read_text())
        compile_inputs.append(local_ref_path.name)
    results.append(run_command(["iverilog", "-g2012", "-o", sim_out.name, *compile_inputs], cwd=workdir))
    if not results[-1].ok:
        return EvaluationResult(False, results, workdir, strength)

    results.append(run_command(["vvp", sim_out.name], cwd=workdir))
    if task.evaluation.pass_regex:
        passed = results[-1].ok and re.search(task.evaluation.pass_regex, results[-1].stdout) is not None
    else:
        passed = results[-1].ok and "PASS" in results[-1].stdout
    return EvaluationResult(passed, results, workdir, strength)
