from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI


def load_local_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    timeout_s: float = 120.0
    max_retries: int = 0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        load_local_env()
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", cls.base_url),
            model=os.environ.get("DEEPSEEK_MODEL", cls.model),
            timeout_s=float(os.environ.get("DEEPSEEK_TIMEOUT_S", cls.timeout_s)),
            max_retries=int(os.environ.get("DEEPSEEK_MAX_RETRIES", cls.max_retries)),
        )


class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout_s,
            max_retries=self.config.max_retries,
        )

    def complete(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            timeout=self.config.timeout_s,
        )
        content = response.choices[0].message.content
        return content or ""
