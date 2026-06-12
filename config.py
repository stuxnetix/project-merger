"""Persistent configuration for Project Merger."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Built-in exclusion rules. Always active unless the user explicitly removes
#: them in the rules dialog (removals are tracked separately, so new built-in
#: rules added in app updates still reach existing users).
DEFAULT_GITIGNORE_PATTERNS: list[str] = [
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
]

DEFAULT_CONFIG: dict[str, Any] = {
    "last_source_dir": str(Path.home()),
    "last_output_dir": str(Path.home()),
    # User-added patterns (on top of the built-in defaults).
    "user_gitignore_patterns": [],
    # Built-in defaults the user explicitly removed in the rules dialog.
    "removed_default_patterns": [],
    "language": "ru",                # UI language: "ru" | "en"
    "sanitize_secrets": False,       # "Очистить секреты" checkbox state
    "max_file_size_kb": 0,           # 0 = no limit
    "recent_projects": [],           # most recent first, capped
}

MAX_RECENT_PROJECTS = 7

CONFIG_PATH = Path.home() / ".project_merger_config.json"


class Config:
    """JSON-backed application configuration."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self._dirty = False
        self.data: dict[str, Any] = {
            k: v.copy() if isinstance(v, list) else v
            for k, v in DEFAULT_CONFIG.items()
        }
        self.load()
        self._migrate_legacy_rules()

    # ───────── persistence ─────────

    def load(self) -> None:
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise json.JSONDecodeError("config root is not an object", "", 0)
                self.data.update(loaded)
                logger.debug("Config loaded from %s (%d keys)", self.path, len(loaded))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load config: %s. Using defaults.", e)

    def save(self) -> None:
        try:
            tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self.path)
            self._dirty = False
            logger.debug("Config saved to %s", self.path)
        except OSError as e:
            logger.error("Failed to save config: %s", e)

    def flush(self) -> None:
        """Write pending changes to disk, if any.

        Directory setters only mark the config dirty instead of writing
        immediately: a synchronous write to the user's home directory (which
        on Windows is often OneDrive-synced and watched by Defender) can stall
        for seconds, and it used to happen right on the folder-selection click
        path. Call ``flush()`` off the hot path (app exit, dialog close).
        """
        if self._dirty:
            self.save()

    def _migrate_legacy_rules(self) -> None:
        """Migrate configs from versions that stored the *full* rule list.

        Older versions persisted the complete pattern list under
        ``default_gitignore``. ``Config.load()`` then shadowed the built-in
        defaults forever, so rules added in app updates (e.g. ``node_modules/``)
        never reached existing users. We keep only genuine user additions and
        re-enable all built-in defaults.
        """
        legacy = self.data.pop("default_gitignore", None)
        if legacy is None:
            return
        defaults = set(DEFAULT_GITIGNORE_PATTERNS)
        user_extra = [p for p in legacy if p not in defaults]
        self.data["user_gitignore_patterns"] = user_extra
        self.data.setdefault("removed_default_patterns", [])
        self.save()
        logger.info(
            "Migrated legacy rule list: %d user patterns kept, built-in defaults re-enabled",
            len(user_extra),
        )

    # ───────── directories ─────────

    @property
    def last_source_dir(self) -> str:
        return self.data.get("last_source_dir", str(Path.home()))

    @last_source_dir.setter
    def last_source_dir(self, value: str) -> None:
        if self.data.get("last_source_dir") != value:
            self.data["last_source_dir"] = value
            self._dirty = True  # written later via flush() — no disk I/O here

    @property
    def last_output_dir(self) -> str:
        return self.data.get("last_output_dir", str(Path.home()))

    @last_output_dir.setter
    def last_output_dir(self, value: str) -> None:
        if self.data.get("last_output_dir") != value:
            self.data["last_output_dir"] = value
            self._dirty = True  # written later via flush() — no disk I/O here

    # ───────── exclusion rules ─────────

    @property
    def gitignore_patterns(self) -> list[str]:
        """Effective exclusion rules: built-in defaults minus removals, plus user additions."""
        removed = set(self.data.get("removed_default_patterns", []))
        patterns = [p for p in DEFAULT_GITIGNORE_PATTERNS if p not in removed]
        seen = set(patterns)
        for p in self.data.get("user_gitignore_patterns", []):
            if p not in seen:
                patterns.append(p)
                seen.add(p)
        return patterns

    def set_gitignore_patterns(self, patterns: list[str]) -> None:
        """Persist the rule list edited by the user."""
        defaults = set(DEFAULT_GITIGNORE_PATTERNS)
        wanted = list(dict.fromkeys(patterns))  # dedupe, keep order
        self.data["user_gitignore_patterns"] = [p for p in wanted if p not in defaults]
        self.data["removed_default_patterns"] = [
            p for p in DEFAULT_GITIGNORE_PATTERNS if p not in set(wanted)
        ]
        self.save()

    # ───────── v3 options ─────────

    @property
    def language(self) -> str:
        lang = self.data.get("language", "ru")
        return lang if lang in ("ru", "en") else "ru"

    @language.setter
    def language(self, value: str) -> None:
        if self.data.get("language") != value:
            self.data["language"] = value
            self._dirty = True

    @property
    def sanitize_secrets(self) -> bool:
        return bool(self.data.get("sanitize_secrets", False))

    @sanitize_secrets.setter
    def sanitize_secrets(self, value: bool) -> None:
        if self.data.get("sanitize_secrets") != bool(value):
            self.data["sanitize_secrets"] = bool(value)
            self._dirty = True

    @property
    def max_file_size_kb(self) -> int:
        try:
            return max(0, int(self.data.get("max_file_size_kb", 0)))
        except (TypeError, ValueError):
            return 0

    @max_file_size_kb.setter
    def max_file_size_kb(self, value: int) -> None:
        value = max(0, int(value))
        if self.data.get("max_file_size_kb") != value:
            self.data["max_file_size_kb"] = value
            self._dirty = True

    @property
    def recent_projects(self) -> list[str]:
        items = self.data.get("recent_projects", [])
        return [str(x) for x in items] if isinstance(items, list) else []

    def add_recent_project(self, path: str) -> None:
        items = [x for x in self.recent_projects if x != path]
        items.insert(0, path)
        self.data["recent_projects"] = items[:MAX_RECENT_PROJECTS]
        self._dirty = True

    def remove_recent_project(self, path: str) -> None:
        items = [x for x in self.recent_projects if x != path]
        if items != self.recent_projects:
            self.data["recent_projects"] = items
            self._dirty = True
