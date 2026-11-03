#!/usr/bin/env bash
set -euo pipefail

rm -f "$HOME/.local/share/applications/home-hub.desktop"
rm -f "$HOME/.config/autostart/home-hub.desktop"
rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/home-hub.png"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

printf 'Removed the Home Hub launcher and autostart entry.\n'
printf 'Your config, cache and application files were left untouched.\n'
