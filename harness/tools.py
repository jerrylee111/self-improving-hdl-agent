from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolResult:
    tool: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def find_tool(name: str) -> str | None:
    return shutil.which(name)


def run_command(command: list[str], cwd: Path | None = None, timeout_s: int = 30) -> ToolResult:
    proc = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    return ToolResult(
        tool=Path(command[0]).name,
        command=command,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def check_hdl_tools() -> dict[str, str | None]:
    return {
        "verilator": find_tool("verilator"),
        "iverilog": find_tool("iverilog"),
        "vvp": find_tool("vvp"),
        "yosys": find_tool("yosys"),
        "sby": find_tool("sby"),
    }
