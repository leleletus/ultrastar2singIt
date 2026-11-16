#!/bin/bash
# Pasa a la Switch SOLO lo que cambió en el parche (letras rehechas, vídeos reconvertidos, canciones nuevas).
#   Por cable (DBI > "Run MTP responder", Switch conectada por USB):   tools/pasar_a_switch.sh
#   Por Wi-Fi (ftpd abierto en la Switch):                             tools/pasar_a_switch.sh 192.168.18.198:5000
#   Solo ver qué copiaría, sin copiar:                                 VER=1 tools/pasar_a_switch.sh [IP:PUERTO]
# Antes valida el parche; si el validador encuentra problemas no copia nada. Se puede cortar y volver a lanzar:
# sigue por donde iba. De los archivos que reemplaza guarda copia en ~/LetsSing/switch_backup_<fecha>/, menos de los
# vídeos (serían decenas de GB; para guardarlos también: CON_COPIA_DE_VIDEOS=1).
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
PATCH="${LETSSING_PATCH:-$HOME/LetsSing/output/0100EE4020D19003}"
PY="$REPO/venv/bin/python"
[ -x "$PY" ] || PY=python3
cd "$REPO" || exit 1
if systemctl --user is-active --quiet letssing-reencode 2>/dev/null; then
    echo "AVISO: la reconversión de vídeos sigue en marcha; se copiará lo que haya hecho hasta ahora"
    echo "       (cuando acabe, vuelve a lanzar esto y pasará el resto)."
fi
echo "=== Validando el parche"
"$PY" tools/validate_patch.py "$PATCH" | tail -n 5
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "El parche tiene problemas: no copio nada."; exit 1; }
args=("$PATCH")
[ -n "$1" ] && args+=(--ftp "$1")
[ -z "$CON_COPIA_DE_VIDEOS" ] && args+=(--no-video-backup)
[ -z "$VER" ] && args+=(--apply)
exec "$PY" tools/switch_update.py "${args[@]}"
