"""Project Merger – entry point."""
from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from config import Config
from ui.main_window import MainWindow


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("project_merger.log", encoding="utf-8"),
        ],
    )


def main() -> None:
    setup_logging()
    app = QApplication(sys.argv)
    config = Config()
    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
