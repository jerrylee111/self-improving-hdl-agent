from __future__ import annotations

import re
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Import VerilogEval raw files into project task YAML files.")
console = Console()


FAMILY_RULES = [
    ("popcount", "combinational_arithmetic", ["combinational", "arithmetic", "popcount"]),
    ("fsm", "sequential_fsm", ["sequential", "fsm", "state_machine"]),
    ("counter", "sequential_counter", ["sequential", "counter"]),
    ("count", "sequential_counter", ["sequential", "counter"]),
    ("dff", "sequential_register", ["sequential", "register", "reset"]),
    ("shift", "sequential_shift", ["sequential", "shift_register"]),
    ("lfsr", "sequential_lfsr", ["sequential", "lfsr"]),
    ("mux", "combinational_mux", ["combinational", "mux"]),
    ("kmap", "combinational_logic", ["combinational", "boolean_logic"]),
    ("gate", "combinational_logic", ["combinational", "boolean_logic"]),
    ("adder", "combinational_arithmetic", ["combinational", "arithmetic"]),
]


def find_raw_root(raw_root: Path) -> Path:
    manifest_path = raw_root / "manifest.yaml"
    if manifest_path.exists():
        manifest = yaml.safe_load(manifest_path.read_text())
        return Path(manifest["raw_path"])
    children = [p for p in raw_root.iterdir() if p.is_dir()]
    if len(children) == 1:
        return children[0]
    raise RuntimeError(f"cannot find VerilogEval raw root under {raw_root}")


def classify(stem: str, prompt: str) -> tuple[str, list[str], int]:
    text = f"{stem} {prompt}".lower()
    family = "misc_hdl"
    tags = ["verilog"]
    for needle, candidate_family, candidate_tags in FAMILY_RULES:
        if needle in text:
            family = candidate_family
            tags.extend(candidate_tags)
            break
    if any(word in text for word in ["clock", "posedge", "reset", "state", "fsm", "counter", "dff"]):
        tags.append("sequential")
    else:
        tags.append("combinational")
    difficulty = 2
    if family.startswith("sequential"):
        difficulty += 1
    if any(word in text for word in ["fsm", "lemmings", "ps2", "rule110", "lfsr"]):
        difficulty += 1
    return family, sorted(set(tags)), min(difficulty, 5)


def split_for_index(index: int) -> str:
    if index % 10 < 6:
        return "evolution"
    if index % 10 < 8:
        return "validation"
    return "holdout"


def problem_number(path: Path) -> int:
    match = re.match(r"Prob(\d+)_", path.name)
    if not match:
        return 0
    return int(match.group(1))


def import_dataset(raw_dataset_dir: Path, out_dir: Path, limit: int | None, dataset_name: str) -> list[Path]:
    prompt_files = sorted(raw_dataset_dir.glob("*_prompt.txt"), key=problem_number)
    written: list[Path] = []
    for index, prompt_path in enumerate(prompt_files):
        if limit is not None and len(written) >= limit:
            break
        stem = prompt_path.name.removesuffix("_prompt.txt")
        test_path = raw_dataset_dir / f"{stem}_test.sv"
        ref_path = raw_dataset_dir / f"{stem}_ref.sv"
        if not test_path.exists() or not ref_path.exists():
            continue
        prompt = prompt_path.read_text().strip()
        family, tags, difficulty = classify(stem, prompt)
        split = split_for_index(len(written))
        task = {
            "id": f"verilogeval_{dataset_name}_{stem.lower()}",
            "source": "verilogeval",
            "license": "verilog-eval",
            "language": "systemverilog",
            "family": family,
            "tags": tags,
            "difficulty": difficulty,
            "prompt": prompt,
            "top_module": "TopModule",
            "ports": [],
            "expected": {"type": "reference_module", "file": str(ref_path)},
            "evaluation": {
                "lint": True,
                "simulation": True,
                "formal": False,
                "testbench_file": str(test_path),
                "pass_regex": r"Mismatches:\s+0\s+in\s+\d+\s+samples",
            },
            "split": {"default": split},
        }
        target = out_dir / split / f"{task['id']}.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
        written.append(target)
    return written


@app.command()
def main(
    raw_root: Path = typer.Option(Path("benchmarks/external/raw/verilogeval"), help="Downloaded VerilogEval root."),
    out_dir: Path = typer.Option(Path("benchmarks/tasks/external/verilogeval"), help="Imported task YAML root."),
    dataset: str = typer.Option("dataset_spec-to-rtl", help="VerilogEval dataset directory to import."),
    limit: int | None = typer.Option(30, help="Maximum task YAML files to create."),
) -> None:
    raw_checkout = find_raw_root(raw_root)
    raw_dataset_dir = raw_checkout / dataset
    if not raw_dataset_dir.exists():
        raise typer.BadParameter(f"missing dataset directory: {raw_dataset_dir}")
    written = import_dataset(raw_dataset_dir, out_dir, limit, dataset.replace("dataset_", "").replace("-", "_"))

    counts: dict[str, int] = {}
    for path in written:
        counts[path.parent.name] = counts.get(path.parent.name, 0) + 1
    table = Table(title="Imported VerilogEval Tasks")
    table.add_column("Split")
    table.add_column("Tasks")
    for split in ["evolution", "validation", "holdout"]:
        table.add_row(split, str(counts.get(split, 0)))
    console.print(table)
    console.print(f"output={out_dir}")


if __name__ == "__main__":
    app()
