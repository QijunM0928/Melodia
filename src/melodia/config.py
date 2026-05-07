"""Configuration management for Melodia."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".melodia"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"


@dataclass
class NeteaseConfig:
    base_url: str = "http://localhost:3000"
    cookie: str = ""


@dataclass
class LLMConfig:
    model: str = "openai/4.0Ultra"
    api_key: str = ""
    api_base: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class MelodiaConfig:
    netease: NeteaseConfig = field(default_factory=NeteaseConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> MelodiaConfig:
    """Load config from YAML file, creating default if not exists."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        save_config(MelodiaConfig(), path)
        return MelodiaConfig()

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    netease_data = data.get("netease", {})
    llm_data = data.get("llm", {})

    return MelodiaConfig(
        netease=NeteaseConfig(**netease_data),
        llm=LLMConfig(**llm_data),
    )


def save_config(config: MelodiaConfig, path: Path = DEFAULT_CONFIG_PATH):
    """Save config to YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    import dataclasses

    def to_dict(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {k: to_dict(v) for k, v in dataclasses.asdict(obj).items()}
        return obj

    with open(path, "w") as f:
        yaml.dump(to_dict(config), f, default_flow_style=False, allow_unicode=True)
