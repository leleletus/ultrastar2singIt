#!/bin/bash
# Adds "Let's Sing UltraStar Converter" to the applications menu (KDE, GNOME, XFCE...): run it once.
# To remove it: rm ~/.local/share/applications/letssing-ultrastar-converter.desktop
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/applications/letssing-ultrastar-converter.desktop"
mkdir -p "$(dirname "$DEST")"
cat > "$DEST" <<EOF
[Desktop Entry]
Type=Application
Name=Let's Sing UltraStar Converter
Comment=Convierte canciones UltraStar para Let's Sing y sincroniza letras
Exec=$APP_DIR/start_linux.sh
Path=$APP_DIR
Icon=$APP_DIR/assets/logo.ico
Terminal=false
Categories=AudioVideo;Audio;
EOF
chmod +x "$APP_DIR/start_linux.sh"
# refresh the KDE menu (other desktops pick the file up by themselves)
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
command -v kbuildsycoca5 >/dev/null && kbuildsycoca5 >/dev/null 2>&1 || true
echo "Listo: busca \"Let's Sing UltraStar Converter\" en el menú de aplicaciones ($DEST)"
