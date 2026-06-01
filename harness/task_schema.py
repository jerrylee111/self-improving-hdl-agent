from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class Port(BaseModel):
    name: str
    dir: Literal["input", "output", "inout"]
    width: int = Field(ge=1)


class Expected(BaseModel):
    type: str
    file: str | None = None


class Evaluation(BaseModel):
    lint: bool = True
    simulation: bool = True
    formal: bool = False


class Split(BaseModel):
    default: str = "dev"


class HDLTask(BaseModel):
    id: str
    source: str = "local_seed"
    license: str = "project-owned"
    language: Literal["verilog", "systemverilog"]
    family: str
    tags: list[str]
    difficulty: int = Field(ge=1, le=5)
    prompt: str
    top_module: str
    ports: list[Port]
    clock: str | None = None
    reset: str | None = None
    expected: Expected
    evaluation: Evaluation = Field(default_factory=Evaluation)
    split: Split = Field(default_factory=Split)


def load_task(path: Path) -> HDLTask:
    data = yaml.safe_load(path.read_text())
    return HDLTask.model_validate(data)
