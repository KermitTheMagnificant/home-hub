#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    printf 'Python executable not found: %s\n' "$PYTHON" >&2
    exit 1
fi

if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
    printf 'pip is not available for %s. Install pip or activate a virtual environment first.\n' "$PYTHON" >&2
    exit 1
fi

"$PYTHON" -m pip install -r "$DIR/requirements.txt"

if ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
    printf '\nPython packages installed, but Tkinter is missing. Install the OS package for your Python:\n' >&2
    printf '  Debian/Ubuntu: sudo apt install python3-tk\n' >&2
    printf '  Fedora:        sudo dnf install python3-tkinter\n' >&2
    printf '  Arch Linux:    sudo pacman -S tk\n' >&2
    exit 1
fi

printf 'Python dependencies are installed and Tkinter is available.\n'