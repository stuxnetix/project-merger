"""GUI-only launcher for Windows — no console window.

Windows associates ``.pyw`` files with ``pythonw.exe``, which runs the
application without opening a terminal. Double-click this file (or make a
desktop shortcut to it) to start Project Merger with GUI only.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make imports work regardless of the directory the shortcut starts in.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import main

if __name__ == "__main__":
    main()
