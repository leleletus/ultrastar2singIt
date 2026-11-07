# -*- mode: python ; coding: utf-8 -*-
# Linux build for the AppImage: a folder (onedir), so the AppImage starts without unpacking itself to /tmp.
# Same contents as "Lets Sing Ultrastar Converter.spec" (the Windows .exe). Run from the repository root:
#     pyinstaller packaging/linux_appimage.spec --noconfirm
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(ROOT, 'LetsSingUltraStarConverter.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, 'config_default.yml'), '.'), (os.path.join(ROOT, 'Guide.md'), '.'),
           (os.path.join(ROOT, 'data/repository/data.db'), 'data/repository'), (os.path.join(ROOT, 'assets'), 'assets'),
           (os.path.join(ROOT, 'locales'), 'locales')],
    hiddenimports=['tools.validate_patch', 'tools.switch_update', 'tools.sync_scan', 'tools.usdb_sources',
                   'tools.fix_covers', 'tools.fix_years', 'tools.fix_genres', 'tools.artist_genders',
                   'tools.usdb_restore_names', 'tools.clean_song_folders', 'tools.align_video', 'tools.make_song'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tensorflow', 'crepe', 'librosa', 'soundfile', 'PySide6.QtWebEngineWidgets', 'PySide6.Qt3DCore',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtOpenGL', 'PySide6.QtBluetooth', 'PySide6.QtDesigner',
              'PySide6.QtHelp', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtXml'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='letssing-converter', debug=False, strip=False, upx=False,
          console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='letssing-converter')
