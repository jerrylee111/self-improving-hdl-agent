from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Summarize and fingerprint candidate skills for deduplication.")
console = Console()


def normalize_payload(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\d+", "<num>", text)
    text = re.sub(r"[^a-z0-9_<>]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_candidates(candidate_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows = []
    for path in sorted(candidate_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        if not data or data.get("version", {}).get("status") != "candidate":
            continue
        rows.append((path, data))
    return rows


def fingerprint(skill: dict[str, Any]) -> str:
    payload = normalize_payload(skill.get("payload", {}).get("content", ""))
    parts = [
        str(skill.get("agent", "")),
        str(skill.get("name", "")),
        str(skill.get("domain", {}).get("language", "")),
        ",".join(sorted(map(str, skill.get("domain", {}).get("topic", [])))),
        ",".join(sorted(map(str, skill.get("task_patterns", [])))),
        payload,
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


@app.command()
def main(
    candidate_dir: Path = typer.Option(Path("skills/candidate"), help="Candidate skill directory."),
    out_path: Path = typer.Option(Path("skills/metrics/candidate_summary.json"), help="Summary JSON output."),
) -> None:
    rows = load_candidates(candidate_dir)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path, skill in rows:
        fp = fingerprint(skill)
        evidence = skill.get("validation", {}).get("evidence", [])
        groups[fp].append(
            {
                "id": skill.get("id"),
                "path": str(path),
                "agent": skill.get("agent"),
                "name": skill.get("name"),
                "task_patterns": skill.get("task_patterns", []),
                "evidence_count": len(evidence),
                "source_tasks": sorted({item.get("task_id") for item in evidence if item.get("task_id")}),
            }
        )

    summary_groups = []
    for fp, items in groups.items():
        task_ids = sorted({task for item in items for task in item["source_tasks"]})
        summary_groups.append(
            {
                "fingerprint": fp,
                "count": len(items),
                "agent": items[0]["agent"],
                "name": items[0]["name"],
                "task_patterns": items[0]["task_patterns"],
                "source_tasks": task_ids,
                "candidate_ids": [item["id"] for item in items],
                "paths": [item["path"] for item in items],
            }
        )
    summary_groups.sort(key=lambda item: (-item["count"], str(item["agent"]), str(item["name"])))

    output = {
        "candidate_count": len(rows),
        "unique_fingerprints": len(summary_groups),
        "duplicate_groups": sum(1 for item in summary_groups if item["count"] > 1),
        "groups": summary_groups,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    table = Table(title="Candidate Skill Fingerprints")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("candidate_count", str(output["candidate_count"]))
    table.add_row("unique_fingerprints", str(output["unique_fingerprints"]))
    table.add_row("duplicate_groups", str(output["duplicate_groups"]))
    console.print(table)
    for item in summary_groups[:10]:
        console.print(
            {
                "fingerprint": item["fingerprint"],
                "count": item["count"],
                "agent": item["agent"],
                "name": item["name"],
                "source_tasks": item["source_tasks"],
            }
        )
    console.print(f"summary={out_path}")


if __name__ == "__main__":
    app()
