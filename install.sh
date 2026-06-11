#!/usr/bin/env bash
set -euo pipefail

echo "Installing Project Merger dependencies..."
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt

echo "Done! Run 'python3 main.py' to start."
