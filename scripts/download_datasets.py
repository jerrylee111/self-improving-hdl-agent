from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Download external HDL benchmark repositories into benchmarks/external/raw.")
console = Console()


@dataclass(frozen=True)
class DatasetRepo:
    key: str
    owner: str
    repo: str
    url: str
    purpose: str


DATASETS = {
    "verilogeval": DatasetRepo(
        key="verilogeval",
        owner="NVlabs",
        repo="verilog-eval",
        url="https://github.com/NVlabs/verilog-eval",
        purpose="HDLBits-style functional correctness benchmark",
    ),
    "rtllm": DatasetRepo(
        key="rtllm",
        owner="hkust-zhiyao",
        repo="RTLLM",
        url="https://github.com/hkust-zhiyao/RTLLM",
        purpose="Natural-language RTL design benchmark",
    ),
}


def run(command: list[str], *, cwd: Path | None = None, stdout: Path | None = None) -> str:
    if stdout is None:
        proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    else:
        with stdout.open("wb") as f:
            proc = subprocess.run(command, cwd=cwd, stdout=f, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.decode() if isinstance(proc.stderr, bytes) else proc.stderr
        raise RuntimeError(f"command failed: {' '.join(command)}\n{stderr}")
    if stdout is not None:
        return ""
    return proc.stdout


def repo_metadata(dataset: DatasetRepo) -> dict:
    raw = run(["gh", "api", f"repos/{dataset.owner}/{dataset.repo}"])
    return json.loads(raw)


def download_tarball(dataset: DatasetRepo, commit: str, dest: Path) -> Path:
    archive = dest / f"{dataset.key}-{commit[:12]}.tar.gz"
    if not archive.exists():
        run(["gh", "api", f"repos/{dataset.owner}/{dataset.repo}/tarball/{commit}"], stdout=archive)
    return archive


def extract_archive(archive: Path, dest: Path) -> Path:
    extract_root = dest / "extract_tmp"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(extract_root)
    children = [p for p in extract_root.iterdir() if p.is_dir()]
    if len(children) != 1:
        raise RuntimeError(f"unexpected archive layout in {archive}")
    return children[0]


def materialize_dataset(dataset: DatasetRepo, raw_root: Path, force: bool) -> dict:
    meta = repo_metadata(dataset)
    default_branch = meta["default_branch"]
    branch = json.loads(run(["gh", "api", f"repos/{dataset.owner}/{dataset.repo}/branches/{default_branch}"]))
    commit = branch["commit"]["sha"]
    dataset_dir = raw_root / dataset.key
    target_dir = dataset_dir / commit
    manifest_path = dataset_dir / "manifest.yaml"
    if target_dir.exists() and not force:
        return yaml.safe_load(manifest_path.read_text())

    dataset_dir.mkdir(parents=True, exist_ok=True)
    archive = download_tarball(dataset, commit, dataset_dir)
    extracted = extract_archive(archive, dataset_dir)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.move(str(extracted), target_dir)
    shutil.rmtree(dataset_dir / "extract_tmp")

    manifest = {
        "key": dataset.key,
        "url": dataset.url,
        "owner": dataset.owner,
        "repo": dataset.repo,
        "default_branch": default_branch,
        "commit": commit,
        "raw_path": str(target_dir),
        "archive": str(archive),
        "purpose": dataset.purpose,
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest


@app.command()
def main(
    dataset: list[str] = typer.Option(["verilogeval", "rtllm"], help="Dataset keys to download."),
    raw_root: Path = typer.Option(Path("benchmarks/external/raw"), help="Raw external dataset root."),
    force: bool = typer.Option(False, help="Re-download and replace existing materialized copy."),
) -> None:
    raw_root.mkdir(parents=True, exist_ok=True)
    manifests = []
    for key in dataset:
        if key not in DATASETS:
            raise typer.BadParameter(f"unknown dataset {key}; valid={sorted(DATASETS)}")
        manifests.append(materialize_dataset(DATASETS[key], raw_root, force))

    table = Table(title="Downloaded External HDL Datasets")
    table.add_column("Dataset")
    table.add_column("Commit")
    table.add_column("Path")
    for manifest in manifests:
        table.add_row(manifest["key"], manifest["commit"][:12], manifest["raw_path"])
    console.print(table)


if __name__ == "__main__":
    app()
