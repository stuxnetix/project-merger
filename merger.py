"""Core logic: file scanning, filtering, markdown generation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import pathspec

logger = logging.getLogger(__name__)

BINARY_INDICATOR = "[двоичный файл]"
EMPTY_INDICATOR = "[пустой файл]"

_CHUNK_SIZE = 8192
_BINARY_THRESHOLD = 0.30
_TEXT_BYTES = bytes(range(32, 127)) + b"\n\r\t\f\b"

LANGUAGE_MAP = {
    ".py": "python",
    ".pyi": "python",
    ".pyx": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".xml": "xml",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "rst",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "bash",
    ".bat": "batch",
    ".cmd": "batch",
    ".ps1": "powershell",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".cs": "csharp",
    ".csx": "csharp",
    ".java": "java",
    ".jsp": "jsp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".erb": "erb",
    ".rake": "ruby",
    ".php": "php",
    ".phtml": "php",
    ".php3": "php",
    ".php4": "php",
    ".php5": "php",
    ".php6": "php",
    ".php7": "php",
    ".php8": "php",
    ".sql": "sql",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sc": "scala",
    ".r": "r",
    ".R": "r",
    ".m": "matlab",
    ".mm": "objectivec",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".t": "perl",
    ".dart": "dart",
    ".vue": "vue",
    ".dockerfile": "dockerfile",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".diff": "diff",
    ".patch": "diff",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".tex": "latex",
    ".cls": "latex",
    ".sty": "latex",
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "makefile": "makefile",
    ".mk": "makefile",
}


def _get_language(file_path: Path) -> str:
    name = file_path.name
    if name in LANGUAGE_MAP:
        return LANGUAGE_MAP[name]
    return LANGUAGE_MAP.get(file_path.suffix.lower(), "")


def _is_binary(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(_CHUNK_SIZE)
    except OSError:
        return True

    if not chunk:
        return False

    if b"\0" in chunk:
        return True

    try:
        chunk.decode("utf-8")
        return False
    except UnicodeDecodeError:
        pass

    nontext = sum(byte not in _TEXT_BYTES for byte in chunk)
    return (nontext / len(chunk)) > _BINARY_THRESHOLD


def _iter_project_files(
    root: Path, spec: pathspec.PathSpec | None, selected_paths: set[Path]
) -> Iterator[Path]:
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        rel_path = item.relative_to(root)
        if any(part == ".git" for part in rel_path.parts):
            continue
        if rel_path.name == ".gitignore":
            continue
        if spec and spec.match_file(str(rel_path)):
            logger.debug("Ignored by .gitignore: %s", rel_path)
            continue
        if selected_paths and rel_path not in selected_paths:
            continue
        yield item


def _build_project_tree(
    root: Path,
    spec: pathspec.PathSpec | None,
    selected_paths: set[Path],
) -> list[str]:
    lines: list[str] = []
    _tree_recurse(root, root, spec, selected_paths, "", lines)
    return lines


def _tree_recurse(
    root: Path,
    directory: Path,
    spec: pathspec.PathSpec | None,
    selected_paths: set[Path],
    prefix: str,
    lines: list[str],
) -> None:
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return

    filtered: list[Path] = []
    for entry in entries:
        rel = entry.relative_to(root)
        if rel.parts and rel.parts[0] in (".git",):
            continue
        if entry.name == ".gitignore":
            continue
        check_path = str(rel) + ("/" if entry.is_dir() else "")
        if spec and spec.match_file(check_path):
            continue
        if selected_paths and entry.is_file() and rel not in selected_paths:
            continue
        if selected_paths and entry.is_dir():
            prefix_match = rel.as_posix() + "/"
            if not any(p.as_posix().startswith(prefix_match) for p in selected_paths):
                continue
        filtered.append(entry)

    for i, entry in enumerate(filtered):
        is_last = i == len(filtered) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _tree_recurse(root, entry, spec, selected_paths, prefix + extension, lines)


def build_markdown(
    root: Path,
    spec: pathspec.PathSpec | None,
    selected_paths: set[Path],
    output_path: Path,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files = list(_iter_project_files(root, spec, selected_paths))
    files_written = 0

    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"# Project: {root.name}\n\n")
        out.write("*Generated by Project Merger*\n\n")
        out.write("---\n\n")

        tree_lines = _build_project_tree(root, spec, selected_paths)
        if tree_lines:
            out.write("## Структура проекта\n\n```\n")
            out.write(f"{root.name}/\n")
            for line in tree_lines:
                out.write(line + "\n")
            out.write("```\n\n---\n\n")

        for file_path in files:
            rel = file_path.relative_to(root)
            logger.info("Processing: %s", rel)

            if _is_binary(file_path):
                out.write(f"## {rel}\n\n{BINARY_INDICATOR}\n\n")
                files_written += 1
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    import chardet

                    raw = file_path.read_bytes()
                    encoding = chardet.detect(raw)["encoding"] or "utf-8"
                    content = raw.decode(encoding)
                except Exception:
                    out.write(f"## {rel}\n\n{BINARY_INDICATOR}\n\n")
                    continue
            except OSError as e:
                logger.error("Read error %s: %s", rel, e)
                out.write(f"## {rel}\n\n*Ошибка чтения файла*\n\n")
                continue

            out.write(f"## {rel}\n\n")

            if not content.strip():
                out.write(f"{EMPTY_INDICATOR}\n\n")
                files_written += 1
                continue

            lang = _get_language(file_path)
            out.write(f"```{lang}\n")
            out.write(content)
            if not content.endswith("\n"):
                out.write("\n")
            out.write("```\n\n")
            files_written += 1

    logger.info("Generated %s with %d files", output_path, files_written)
    return files_written
