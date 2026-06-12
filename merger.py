"""Core logic: file collection, binary detection, markdown generation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pathspec

from i18n import tr
from sanitizer import Finding, sanitize_text
from scanner import FsNode, ScanCancelled, iter_file_nodes, scan_tree

try:  # optional dependency for non-UTF-8 fallback decoding
    import chardet
except ImportError:  # pragma: no cover
    chardet = None

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Outcome of :func:`build_markdown`."""

    files_written: int = 0
    total_chars: int = 0                 # embedded content size (for token estimate)
    sanitized: bool = False
    findings: dict[str, list[Finding]] = field(default_factory=dict)  # rel_path -> findings
    skipped_oversize: list[str] = field(default_factory=list)

    @property
    def findings_count(self) -> int:
        return sum(len(v) for v in self.findings.values())

    @property
    def token_estimate(self) -> int:
        """Rough LLM token estimate (≈4 chars/token for code)."""
        return self.total_chars // 4


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
    sanitize: bool = False,
    max_file_size_kb: int = 0,
) -> MergeResult:
    """Generate the merged markdown document.

    ``selected_paths`` is a set of POSIX-style relative paths; empty set means
    "all files". A single pruned filesystem walk feeds both the project tree
    and the file list. With ``sanitize=True`` secrets are masked via
    :mod:`sanitizer`; ``max_file_size_kb > 0`` skips larger files with a note.
    Returns a :class:`MergeResult`.

    Raises :class:`ScanCancelled` if cancelled via ``cancel_check``.
    """
    root = Path(root)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_resolved = output_path.resolve()

    fs_root, _ = scan_tree(root, spec, cancel_check=cancel_check)
    filtered_root = _filter_node(fs_root, selected_paths)

    file_nodes = list(iter_file_nodes(filtered_root)) if filtered_root else []
    result = MergeResult(sanitized=sanitize)

    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"# Project: {root.name}\n\n")
        out.write("*Generated by Project Merger*\n\n")
        out.write("---\n\n")

        if filtered_root is not None and filtered_root.children:
            tree_lines = _render_tree_lines(filtered_root)
            out.write(f"## {tr('doc_tree_header')}\n\n```\n")
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

            if max_file_size_kb > 0:
                try:
                    size_kb = file_path.stat().st_size // 1024
                except OSError:
                    size_kb = 0
                if size_kb > max_file_size_kb:
                    out.write(tr("doc_skipped_size", size=size_kb, limit=max_file_size_kb) + "\n\n")
                    result.skipped_oversize.append(node.rel_path)
                    result.files_written += 1
                    continue

            if _is_binary(file_path):
                out.write(f"{tr('doc_binary')}\n\n")
                result.files_written += 1
                continue

            content = _read_text(file_path)
            if content is None:
                out.write(f"{tr('doc_read_error')}\n\n")
                continue

            if not content.strip():
                out.write(f"{tr('doc_empty')}\n\n")
                result.files_written += 1
                continue

            if sanitize:
                content, findings = sanitize_text(content)
                if findings:
                    result.findings[node.rel_path] = findings

            lang = _get_language(file_path)
            out.write(f"```{lang}\n")
            out.write(content)
            if not content.endswith("\n"):
                out.write("\n")
            out.write("```\n\n")
            result.total_chars += len(content)
            result.files_written += 1

        if sanitize and result.findings_count:
            out.write(tr("doc_sanitize_note", n=result.findings_count) + "\n")

    logger.info(
        "Generated %s with %d files (sanitized=%s, masked=%d)",
        output_path, result.files_written, sanitize, result.findings_count,
    )
    return result
