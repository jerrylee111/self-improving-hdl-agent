from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import typer
import yaml
from rich.console import Console
from rich.table import Table

from scripts.summarize_candidate_skills import fingerprint, load_candidates

app = typer.Typer(help="Merge duplicate candidate skill files into candidate blocks.")
console = Console()


def _merge_group(fp: str, rows: list[tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    first = rows[0][1]
    evidence = []
    parent_ids = []
    source_paths = []
    for path, skill in rows:
        parent_ids.append(skill["id"])
        source_paths.append(str(path))
        evidence.extend(skill.get("validation", {}).get("evidence", []))
    seen = set()
    unique_evidence = []
    for item in evidence:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        unique_evidence.append(item)

    block_id = f"candidate_block.{first.get('agent')}.{first.get('name')}.{fp}"
    return {
        "id": block_id,
        "name": first.get("name"),
        "agent": first.get("agent"),
        "domain": first.get("domain", {}),
        "task_patterns": first.get("task_patterns", []),
        "preconditions": first.get("preconditions", []),
        "anti_patterns": first.get("anti_patterns", []),
        "payload": first.get("payload", {}),
        "metrics": {
            "uses": 0,
            "successes": 0,
            "failures": 0,
            "utility_ema": 0.0,
            "token_cost_ema": 0.0,
            "merged_candidate_count": len(rows),
            "evidence_count": len(unique_evidence),
        },
        "cache": first.get("cache", {"pin": False}),
        "version": {
            "status": "candidate_block",
            "revision": 1,
            "parent_ids": parent_ids,
            "fingerprint": fp,
        },
        "validation": {"evidence": unique_evidence},
        "provenance": {"source_paths": source_paths},
    }


@app.command()
def main(
    candidate_dir: Path = typer.Option(Path("skills/candidate"), help="Candidate skill directory."),
    out_dir: Path = typer.Option(Path("skills/candidate_blocks"), help="Merged candidate block directory."),
    min_count: int = typer.Option(1, help="Minimum group size to materialize."),
) -> None:
    rows = load_candidates(candidate_dir)
    grouped: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path, skill in rows:
        grouped.setdefault(fingerprint(skill), []).append((path, skill))

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for fp, group in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(group) < min_count:
            continue
        block = _merge_group(fp, group)
        target = out_dir / f"{block['id']}.yaml"
        target.write_text(yaml.safe_dump(block, sort_keys=False, allow_unicode=True))
        written.append((target, block))

    table = Table(title="Merged Candidate Blocks")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("source_candidates", str(len(rows)))
    table.add_row("fingerprints", str(len(grouped)))
    table.add_row("blocks_written", str(len(written)))
    console.print(table)
    for path, block in written[:10]:
        console.print(
            {
                "id": block["id"],
                "merged_candidate_count": block["metrics"]["merged_candidate_count"],
                "evidence_count": block["metrics"]["evidence_count"],
                "path": str(path),
            }
        )


if __name__ == "__main__":
    app()
