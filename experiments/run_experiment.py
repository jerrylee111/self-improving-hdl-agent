from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Run HDL agent experiments.")
console = Console()


@app.command()
def main(
    config: Path = typer.Argument(..., help="Path to an experiment config YAML file."),
    dry_run: bool = typer.Option(True, help="Only validate config path."),
) -> None:
    console.print(
        {
            "config": str(config),
            "config_exists": config.exists(),
            "dry_run": dry_run,
        }
    )
    if not config.exists():
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
