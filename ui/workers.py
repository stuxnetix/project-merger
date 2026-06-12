"""Background workers (QThread) for scanning and markdown generation.

Note: signal names deliberately do NOT shadow the built-in ``QThread.finished``
signal — overriding it breaks Qt's thread-lifecycle notifications.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from merger import build_markdown
from scanner import ScanCancelled, scan_tree

logger = logging.getLogger(__name__)


class CancellableWorker(QThread):
    """Base class with cooperative cancellation."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


class ScanWorker(CancellableWorker):
    """Scans the project tree off the GUI thread."""

    scan_done = Signal(object, int)  # (FsNode root, item count)
    scan_failed = Signal(str)
    scan_progress = Signal(int, str)  # (items so far, current relative path)

    def __init__(self, root: Path, spec, parent=None) -> None:
        super().__init__(parent)
        self._root = root
        self._spec = spec

    def run(self) -> None:
        try:
            node, count = scan_tree(
                self._root,
                self._spec,
                cancel_check=self.is_cancelled,
                progress_callback=self.scan_progress.emit,
            )
        except ScanCancelled:
            logger.info("Scan cancelled by user")
            return
        except Exception as e:  # noqa: BLE001 — surface any failure to the UI
            logger.exception("Scan failed")
            self.scan_failed.emit(str(e))
            return
        if not self.is_cancelled():
            logger.info("Scan finished: %d items", count)
            self.scan_done.emit(node, count)


class MergerWorker(CancellableWorker):
    """Generates the merged markdown document off the GUI thread."""

    merge_done = Signal(object)  # MergeResult
    merge_failed = Signal(str)
    merge_progress = Signal(int, str)  # (file index, relative path)

    def __init__(
        self,
        root: Path,
        spec,
        selected: set[str],
        output: Path,
        sanitize: bool = False,
        max_file_size_kb: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._root = root
        self._spec = spec
        self._selected = selected
        self._output = output
        self._sanitize = sanitize
        self._max_file_size_kb = max_file_size_kb

    def run(self) -> None:
        try:
            result = build_markdown(
                self._root,
                self._spec,
                self._selected,
                self._output,
                cancel_check=self.is_cancelled,
                progress_callback=self.merge_progress.emit,
                sanitize=self._sanitize,
                max_file_size_kb=self._max_file_size_kb,
            )
        except ScanCancelled:
            logger.info("Merge cancelled by user")
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("Merge failed")
            self.merge_failed.emit(str(e))
            return
        if not self.is_cancelled():
            self.merge_done.emit(result)
