#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3 || true)"

if [ -z "$PYTHON" ]; then
    printf 'python3 was not found in PATH.\n' >&2
    exit 1
fi
if ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
    printf 'Tkinter is required. Install python3-tk (Fedora) or python3-tkinter (Debian/Ubuntu).\n' >&2
    exit 1
fi

chmod +x "$DIR/hub.py"

mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.config/autostart"
mkdir -p "$HOME/.local/share/icons/hicolor/256x256/apps"
cp "$DIR/assets/home-hub.png" "$HOME/.local/share/icons/hicolor/256x256/apps/home-hub.png"

DESKTOP="$(mktemp)"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Home Hub
Comment=Clock, weather, last-24h news and app shortcuts
Exec="$PYTHON" "$DIR/hub.py"
Icon=home-hub
Terminal=false
Categories=Utility;
StartupNotify=false
EOF

install -m 0644 "$DESKTOP" "$HOME/.local/share/applications/home-hub.desktop"
install -m 0644 "$DESKTOP" "$HOME/.config/autostart/home-hub.desktop"
rm -f "$DESKTOP"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

"$PYTHON" -c 'import requests' >/dev/null 2>&1 || \
    printf 'Note: the "requests" package is missing; install it with: %s -m pip install requests\n' "$PYTHON" >&2
"$PYTHON" -c 'import PIL' >/dev/null 2>&1 || \
    printf 'Note: Pillow is missing; shortcuts will use monograms. Install it with: %s -m pip install Pillow\n' "$PYTHON" >&2

printf 'Installed Home Hub.\n'
printf '  Launcher: %s\n' "$HOME/.local/share/applications/home-hub.desktop"
printf '  Autostart: %s\n' "$HOME/.config/autostart/home-hub.desktop"
printf 'Start it now with: %s %s/hub.py\n' "$PYTHON" "$DIR"
