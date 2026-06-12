"""Fast, cancellable filesystem scanning with gitignore-aware pruning.

Pure-Python module (no Qt imports) so it is trivially unit-testable.

Key properties:
- ``os.scandir`` based: directory-entry type comes from the OS dirent data,
  no extra ``stat()`` round-trips per file (important on Windows/NTFS).
- Ignored directories are *pruned*: the walker never descends into them
  (matching git semantics — children of an excluded directory cannot be
  re-included).
- Cooperative cancellation via a ``cancel_check`` callable.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

import pathspec

logger = logging.getLogger(__name__)

#: Names that are never shown nor merged, regardless of rules.
ALWAYS_SKIPPED_NAMES = frozenset({".git", ".gitignore"})


class ScanCancelled(Exception):
    """Raised internally when the caller requested cancellation."""


@dataclass(slots=True)
class FsNode:
    """Lightweight filesystem tree node."""

    name: str
    rel_path: str  # POSIX-style path relative to the scan root ("" for root)
    is_dir: bool
    children: list["FsNode"] = field(default_factory=list)


def scan_tree(
    root: Path,
    spec: pathspec.PathSpec | None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
    progress_every: int = 200,
) -> tuple[FsNode, int]:
    """Scan ``root`` into an :class:`FsNode` tree, skipping ignored entries.

    Returns ``(root_node, item_count)``. Raises :class:`ScanCancelled` if
    ``cancel_check`` returns True during the walk.
    """
    root = Path(root)
    root_node = FsNode(name=root.name or str(root), rel_path="", is_dir=True)
    count = 0

    def _scan(dir_path: str, rel_prefix: str, node: FsNode) -> None:
        nonlocal count
        if cancel_check is not None and cancel_check():
            raise ScanCancelled
        try:
            with os.scandir(dir_path) as it:
                entries = sorted(
                    it,
                    key=lambda e: (not _safe_is_dir(e), e.name.lower()),
                )
        except OSError as e:
            logger.debug("scan: cannot read %s: %s", dir_path, e)
            return

        for entry in entries:
            if cancel_check is not None and cancel_check():
                raise ScanCancelled
            name = entry.name
            if name in ALWAYS_SKIPPED_NAMES:
                continue
            is_dir = _safe_is_dir(entry)
            rel = rel_prefix + name
            match_path = rel + "/" if is_dir else rel
            if spec is not None and spec.match_file(match_path):
                logger.debug("scan: ignored %s", match_path)
                continue  # pruned — never descend into ignored directories

            child = FsNode(name=name, rel_path=rel, is_dir=is_dir)
            node.children.append(child)
            count += 1
            if progress_callback is not None and count % progress_every == 0:
                progress_callback(count, rel)

            if is_dir and not _safe_is_symlink(entry):
                # Symlinked dirs are listed but not followed (avoids cycles).
                _scan(entry.path, rel + "/", child)

    _scan(str(root), "", root_node)
    return root_node, count


def iter_file_nodes(node: FsNode) -> Iterator[FsNode]:
    """Yield all file nodes of the tree in depth-first order."""
    for child in node.children:
        if child.is_dir:
            yield from iter_file_nodes(child)
        else:
            yield child


def _safe_is_dir(entry: os.DirEntry) -> bool:
    try:
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return False


def _safe_is_symlink(entry: os.DirEntry) -> bool:
    try:
        return entry.is_symlink()
    except OSError:
        return True  # be conservative: do not descend
