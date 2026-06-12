"""Core logic: file collection, binary detection, markdown generation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import pathspec

from scanner import FsNode, ScanCancelled, iter_file_nodes, scan_tree

try:  # optional dependency for non-UTF-8 fallback decoding
    import chardet
except ImportError:  # pragma: no cover
    chardet = None

logger = logging.getLogger(__name__)

BINARY_INDICATOR = "[двоичный файл]"
EMPTY_INDICATOR = "[пустой файл]"
READ_ERROR_INDICATOR = "*Ошибка чтения файла*"

_CHUNK_SIZE = 8192
_BINARY_THRESHOLD = 0.30
# Bytes considered "text": printable ASCII, common whitespace and ALL high bytes
# (0x80–0xFF) — those are valid letters in legacy encodings such as cp1251;
# counting them as binary used to mark Russian non-UTF-8 files as [двоичный файл].
_TEXT_BYTES = bytes(range(32, 127)) + b"\n\r\t\f\b" + bytes(range(128, 256))

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
    # bytes.translate with delete table is C-speed, unlike a per-byte Python loop
    nontext = len(chunk.translate(None, _TEXT_BYTES))
    return (nontext / len(chunk)) > _BINARY_THRESHOLD


def _read_text(file_path: Path) -> str | None:
    """Read a text file, falling back to chardet for non-UTF-8 encodings."""
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        if chardet is None:
            return None
        try:
            raw = file_path.read_bytes()
            encoding = chardet.detect(raw)["encoding"] or "utf-8"
            return raw.decode(encoding)
        except (OSError, LookupError, UnicodeDecodeError):
            return None


def _filter_node(node: FsNode, selected: set[str]) -> FsNode | None:
    """Return a copy of the tree containing only selected files (and their dirs).

    With an empty selection the tree is returned as-is.
    """
    if not selected:
        return node
    if not node.is_dir:
        return node if node.rel_path in selected else None
    kept = [c for c in (_filter_node(ch, selected) for ch in node.children) if c is not None]
    if not kept:
        return None
    return FsNode(name=node.name, rel_path=node.rel_path, is_dir=True, children=kept)


def _render_tree_lines(node: FsNode, prefix: str = "", lines: list[str] | None = None) -> list[str]:
    if lines is None:
        lines = []
    for i, child in enumerate(node.children):
        is_last = i == len(node.children) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{child.name}{'/' if child.is_dir else ''}")
        if child.is_dir:
            extension = "    " if is_last else "│   "
            _render_tree_lines(child, prefix + extension, lines)
    return lines


def build_markdown(
    root: Path,
    spec: pathspec.PathSpec | None,
    selected_paths: set[str],
    output_path: Path,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> int:
    """Generate the merged markdown document.

    ``selected_paths`` is a set of POSIX-style relative paths; empty set means
    "all files". A single pruned filesystem walk feeds both the project tree
    and the file list. Returns the number of files written.

    Raises :class:`ScanCancelled` if cancelled via ``cancel_check``.
    """
    root = Path(root)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_resolved = output_path.resolve()

    fs_root, _ = scan_tree(root, spec, cancel_check=cancel_check)
    filtered_root = _filter_node(fs_root, selected_paths)

    file_nodes = list(iter_file_nodes(filtered_root)) if filtered_root else []
    files_written = 0

    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"# Project: {root.name}\n\n")
        out.write("*Generated by Project Merger*\n\n")
        out.write("---\n\n")

        if filtered_root is not None and filtered_root.children:
            tree_lines = _render_tree_lines(filtered_root)
            out.write("## Структура проекта\n\n```\n")
            out.write(f"{root.name}/\n")
            for line in tree_lines:
                out.write(line + "\n")
            out.write("```\n\n---\n\n")

        for index, node in enumerate(file_nodes, start=1):
            if cancel_check is not None and cancel_check():
                raise ScanCancelled
            file_path = root / node.rel_path
            if file_path.resolve() == output_resolved:
                continue  # never merge the output file into itself
            if progress_callback is not None:
                progress_callback(index, node.rel_path)
            logger.debug("Processing: %s", node.rel_path)

            out.write(f"## {node.rel_path}\n\n")

            if _is_binary(file_path):
                out.write(f"{BINARY_INDICATOR}\n\n")
                files_written += 1
                continue

            content = _read_text(file_path)
            if content is None:
                out.write(f"{READ_ERROR_INDICATOR}\n\n")
                continue

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
