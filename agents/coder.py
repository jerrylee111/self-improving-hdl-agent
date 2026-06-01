from __future__ import annotations

import re

from agents.llm import LLMClient
from harness.task_schema import HDLTask


def _format_ports(task: HDLTask) -> str:
    return "\n".join(f"- {p.dir} [{p.width - 1}:0] {p.name}" if p.width > 1 else f"- {p.dir} {p.name}" for p in task.ports)


def _format_skills(skills: list[dict]) -> str:
    blocks = []
    for skill in skills:
        payload = skill.get("payload", {})
        blocks.append(f"[{skill.get('id')}]\n{payload.get('content', '')}")
    return "\n\n".join(blocks)


def extract_verilog(text: str) -> str:
    fenced = re.search(r"```(?:systemverilog|verilog|sv)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    module = re.search(r"(module\s+.*?endmodule)", text, re.DOTALL)
    if module:
        return module.group(1).strip()
    return text.strip()


def generate_rtl(
    task: HDLTask,
    skills: list[dict],
    llm: LLMClient,
    previous_rtl: str | None = None,
    feedback: str | None = None,
) -> str:
    system = (
        "You are a senior RTL engineer. Generate only synthesizable Verilog/SystemVerilog code. "
        "Return exactly one module and no explanation."
    )
    user = f"""
Task:
{task.prompt}

Required top module: {task.top_module}
Language: {task.language}
Ports:
{_format_ports(task)}

Retrieved skills:
{_format_skills(skills)}

Constraints:
- Preserve module name and ports exactly.
- Do not include a testbench.
- Return code only.
"""
    if previous_rtl and feedback:
        user += f"""

Previous RTL:
```verilog
{previous_rtl}
```

Evaluator feedback:
{feedback}

Repair the RTL with the smallest necessary change. Return the complete corrected module only.
"""
    return extract_verilog(llm.complete(system=system, user=user))
