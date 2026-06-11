"""Handling of .gitignore files for project filtering."""
from __future__ import annotations

import logging
from pathlib import Path

import pathspec

logger = logging.getLogger(__name__)

DEFAULT_GITIGNORE_NAME = ".gitignore"


def get_gitignore_spec(root_dir: Path) -> pathspec.PathSpec | None:
    """Parse .gitignore in root_dir, returning a PathSpec if it exists."""
    gitignore_path = root_dir / DEFAULT_GITIGNORE_NAME
    if not gitignore_path.is_file():
        return None
    try:
        with open(gitignore_path, "r", encoding="utf-8") as f:
            spec = pathspec.PathSpec.from_lines("gitwildmatch", f)
        logger.info("Loaded .gitignore from %s", gitignore_path)
        return spec
    except OSError as e:
        logger.error("Failed to read .gitignore: %s", e)
        return None


def get_combined_spec(root_dir: Path, extra_patterns: list[str]) -> pathspec.PathSpec:
    """Merge .gitignore patterns with extra patterns into one PathSpec."""
    gitignore_path = root_dir / DEFAULT_GITIGNORE_NAME
    patterns: list[str] = []
    if gitignore_path.is_file():
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        patterns.append(stripped)
        except OSError as e:
            logger.error("Failed to read .gitignore: %s", e)
    patterns.extend(extra_patterns)
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def create_default_gitignore(root_dir: Path, patterns: list[str]) -> bool:
    """Write default .gitignore with given patterns. Returns True on success."""
    gitignore_path = root_dir / DEFAULT_GITIGNORE_NAME
    try:
        content = "\n".join(patterns) + "\n"
        gitignore_path.write_text(content, encoding="utf-8")
        logger.info("Created default .gitignore at %s", gitignore_path)
        return True
    except OSError as e:
        logger.error("Failed to create .gitignore: %s", e)
        return False
