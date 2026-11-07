#!/bin/sh
# Builds dist/LetsSingConverter-<version>-x86_64.AppImage inside Debian 12 (glibc 2.36), so it runs on any Linux
# from the last years, not only on the newer one it was built on. Needs podman (or docker: CONTAINER=docker).
# Usage (from the repository root): sh packaging/build_appimage.sh
set -eu
CONTAINER=${CONTAINER:-podman}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' "$ROOT/version.py")
mkdir -p "$ROOT/dist"
"$CONTAINER" run --rm --memory=6g -v "$ROOT:/src:ro" -v "$ROOT/dist:/out" -e VERSION="$VERSION" \
    docker.io/library/python:3.13-bookworm sh -euc '
    apt-get update -qq && apt-get install -y -qq --no-install-recommends file binutils libegl1 libgl1 libxkbcommon0 \
        libfontconfig1 libdbus-1-3 >/dev/null
    mkdir /build && git -c safe.directory="*" -C /src archive HEAD | tar -x -C /build && cd /build
    pip install -q --root-user-action=ignore -r requirements.txt pyinstaller
    QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t . 2>&1 | tail -3
    pyinstaller packaging/linux_appimage.spec --noconfirm --distpath /build/pyi --workpath /build/pyi-work >/dev/null 2>&1
    APPDIR=/build/AppDir
    mkdir -p $APPDIR/usr
    cp -r /build/pyi/letssing-converter $APPDIR/usr/lib
    python -c "from PIL import Image; Image.open(\"assets/logo.ico\").convert(\"RGBA\").resize((256, 256)).save(\"$APPDIR/letssing-converter.png\")"
    cat > $APPDIR/letssing-converter.desktop <<DESKTOP
[Desktop Entry]
Type=Application
Name=Let'"'"'s Sing UltraStar Converter
Comment=UltraStar songs to Let'"'"'s Sing (Nintendo Switch)
Exec=letssing-converter
Icon=letssing-converter
Categories=AudioVideo;
Terminal=false
DESKTOP
    cat > $APPDIR/AppRun <<APPRUN
#!/bin/sh
HERE=\$(dirname "\$(readlink -f "\$0")")
exec "\$HERE/usr/lib/letssing-converter" "\$@"
APPRUN
    chmod +x $APPDIR/AppRun
    curl -sSL -o /build/appimagetool https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x /build/appimagetool
    ARCH=x86_64 /build/appimagetool --appimage-extract-and-run $APPDIR /out/LetsSingConverter-$VERSION-x86_64.AppImage >/dev/null 2>&1
    ls -la /out
'
