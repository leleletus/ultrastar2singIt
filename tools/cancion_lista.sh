#!/bin/bash
# Después de corregir una canción a oído en el editor (palabras movidas, clonadas, partidas, duraciones): rehace el
# tono de todas las notas desde la voz, avisa de notas que se pisan, la marca como revisada, la vuelve a convertir
# al parche (solo letra/notas; el vídeo .bk2 no se toca) y valida el parche.
#   Uso:      tools/cancion_lista.sh "Paty Cantú - Suerte"        (carpeta de la canción o parte del nombre)
#             tools/cancion_lista.sh "Suerte" "Iris" "Who Knew"    (varias a la vez)
#             PROBAR=1 tools/cancion_lista.sh "Suerte"             (solo enseña qué tonos cambiarían; no escribe nada)
# Carpetas: LETSSING_SONGS (por defecto ~/LetsSing/songs) y LETSSING_PATCH (~/LetsSing/output/0100EE4020D19003).
# El txt de antes queda en <songs>/../_respaldo_songmaker/<fecha>_<canción>/.
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
SONGS="${LETSSING_SONGS:-$HOME/LetsSing/songs}"
PATCH="${LETSSING_PATCH:-$HOME/LetsSing/output/0100EE4020D19003}"
PY="$REPO/venv/bin/python"
[ -x "$PY" ] || PY=python3
[ $# -ge 1 ] || { sed -n '2,9p' "$0"; exit 1; }
cd "$REPO" || exit 1
names=()
for want in "$@"; do
    want="${want%/}"; want="${want##*/}"
    if [ -d "$SONGS/$want" ]; then
        names+=("$want")
        continue
    fi
    mapfile -t found < <(ls "$SONGS" | grep -i -F -- "$want")
    if [ ${#found[@]} -eq 1 ]; then
        names+=("${found[0]}")
    elif [ ${#found[@]} -eq 0 ]; then
        echo "No encuentro ninguna canción con «$want» en $SONGS"; exit 1
    else
        echo "«$want» coincide con varias; escribe más del nombre:"; printf '   %s\n' "${found[@]}"; exit 1
    fi
done
for name in "${names[@]}"; do
    echo "=== $name: tonos"
    if [ -n "$PROBAR" ]; then
        "$PY" tools/after_review.py "$SONGS/$name" || exit 1
    else
        "$PY" tools/after_review.py "$SONGS/$name" --apply --checked || exit 1
    fi
done
[ -n "$PROBAR" ] && exit 0
echo "=== Convirtiendo al parche: ${names[*]}"
"$PY" - "${names[@]}" <<'PYEOF' || { echo "LA CONVERSIÓN FALLÓ (mira los mensajes de arriba)"; exit 1; }
import logging, sys
sys.path.insert(0, '.')
import ConvertFiles
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.WARNING)
logging.getLogger().addHandler(handler)
ConvertFiles.main(only_dirs=sys.argv[1:])
PYEOF
echo "=== Validando el parche"
"$PY" tools/validate_patch.py "$PATCH" | tail -n 5
echo
echo "Hecho. Para pasarla a la Switch: tools/pasar_a_switch.sh   (por cable)   o   tools/pasar_a_switch.sh 192.168.18.198:5000   (FTP)"
