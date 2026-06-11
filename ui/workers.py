"""Background worker for markdown generation."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from merger import build_markdown

logger = logging.getLogger(__name__)


class MergerWorker(QThread):
    finished = Signal(int)
    error = Signal(str)

    def __init__(
        self,
        root: Path,
        spec,
        selected: set[Path],
        output: Path,
    ) -> None:
        super().__init__()
        self.root = root
        self.spec = spec
        self.selected = selected
        self.output = output

    def run(self) -> None:
        try:
            count = build_markdown(self.root, self.spec, self.selected, self.output)
            self.finished.emit(count)
        except Exception as e:
            logger.exception("Merge failed")
            self.error.emit(str(e))
