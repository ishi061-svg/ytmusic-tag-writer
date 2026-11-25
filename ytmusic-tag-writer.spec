# -*- mode: python ; coding: utf-8 -*-
# exe を作る設定。作り方：python -m PyInstaller ytmusic-tag-writer.spec
from PyInstaller.utils.hooks import collect_all

datas = [('icon.ico', '.'), ('icon.png', '.')]  # icon.png は画面の左上の絵に使う
binaries = []
hiddenimports = []
for pkg in ('tkinterdnd2', 'ytmusicapi'):   # ドラッグ＆ドロップの部品と、YouTube Music の部品を丸ごと入れる
    ret = collect_all(pkg)
    datas += ret[0]; binaries += ret[1]; hiddenimports += ret[2]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ytmusic-tag-writer',
    icon='icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
