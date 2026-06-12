"""Project Merger – entry point."""
from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication

from config import Config
from ui.main_window import MainWindow


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("project_merger.log", encoding="utf-8", mode="w"),
        ],
    )
    for name in ("PySide6", "shiboken6"):
        logging.getLogger(name).setLevel(logging.WARNING)


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
