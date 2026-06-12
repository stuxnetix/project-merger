"""Project Merger – entry point."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from config import Config
from ui.main_window import MainWindow

LOG_PATH = Path(__file__).resolve().parent / "project_merger.log"


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    # Log file lives next to the script (CWD may differ when launched via a
    # shortcut). Under pythonw.exe there is no console: sys.stdout is None,
    # so the stream handler must be skipped or every log call would fail.
    handlers: list[logging.Handler] = [
        logging.FileHandler(LOG_PATH, encoding="utf-8", mode="w"),
    ]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    for name in ("PySide6", "shiboken6"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Under pythonw uncaught exceptions are otherwise silently swallowed.
    def _log_uncaught(exc_type, exc, tb) -> None:
        logging.getLogger("main").critical(
            "Uncaught exception", exc_info=(exc_type, exc, tb)
        )

    sys.excepthook = _log_uncaught


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project Merger")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable verbose debug logging (slows down large scans)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(debug=args.debug)
    logger = logging.getLogger("main")
    logger.info("=== Application starting ===")
    app = QApplication(sys.argv)
    config = Config()
    window = MainWindow(config)
    window.show()
    logger.info("=== Main window shown ===")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
