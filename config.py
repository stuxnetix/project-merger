"""Persistent configuration for Project Merger."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "last_source_dir": str(Path.home()),
    "last_output_dir": str(Path.home()),
    "default_gitignore": [
        "__pycache__/",
        "venv/",
        "env/",
        ".ve*/",
        ".eggs*/",
        "*.egg-info/",
        ".cache*/",
        ".mypy_cache/",
        ".pytest_cache*/",
        ".ruff_cache/",
        ".tox/",
        ".nox/",
        "htmlcov/",
        "build/",
        "dist/",
        "pip-wheel-metadata/",
        "*.py[cod]",
        "*.so",
        "node_modules/",
        ".next/",
        ".nuxt/",
        ".svelte-kit/",
        ".parcel-cache/",
        ".turbo/",
        ".vercel/",
        "coverage/",
        "out/",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        ".git/",
        ".svn/",
        ".hg/",
        ".idea/",
        ".idea_modules/",
        ".kilo/",
        ".cursor/",
        ".vscode/",
        ".reports*/",
        "logs/",
        ".qwen/",
        ".DS_Store",
        "Thumbs.db",
        ".coverage",
        "*.log",
        "*.tmp",
        "project_merged.md",
        "project_merger.log",
        ".project_merger_config.json",
    ],
}

CONFIG_PATH = Path.home() / ".project_merger_config.json"


class Config:
    """Singleton-like configuration handler."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self.data: dict[str, Any] = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.data.update(loaded)
                logger.info("Configuration loaded from %s", self.path)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load config: %s. Using defaults.", e)

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            logger.info("Configuration saved to %s", self.path)
        except OSError as e:
            logger.error("Failed to save config: %s", e)

    @property
    def last_source_dir(self) -> str:
        return self.data.get("last_source_dir", str(Path.home()))

    @last_source_dir.setter
    def last_source_dir(self, value: str) -> None:
        self.data["last_source_dir"] = value
        self.save()

    @property
    def last_output_dir(self) -> str:
        return self.data.get("last_output_dir", str(Path.home()))

    @last_output_dir.setter
    def last_output_dir(self, value: str) -> None:
        self.data["last_output_dir"] = value
        self.save()

    @property
    def default_gitignore_patterns(self) -> list[str]:
        return self.data.get("default_gitignore", DEFAULT_CONFIG["default_gitignore"])
