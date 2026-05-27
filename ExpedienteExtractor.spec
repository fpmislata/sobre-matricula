# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('models', 'models'), ('modules', 'modules'), ('utils', 'utils'), ('gui', 'gui'), ('.venv/Lib/site-packages/cv2/data', 'cv2/data')]
binaries = []
hiddenimports = ['main', 'config', 'cv2', 'pymupdf', 'Levenshtein', 'requests', 'gui.app', 'gui.theme', 'gui.config_manager', 'gui.flet_compat', 'gui.processing_manager', 'gui.processing_worker', 'gui.review_manager', 'gui.system_utils', 'gui.views.inicio_simple', 'gui.views.inicio', 'gui.views.configuracion', 'gui.views.logs', 'gui.views.output', 'gui.views.review_dialog']
tmp_ret = collect_all('flet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('flet_desktop')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('ultralytics')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['gui_main.py'],
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
    [],
    exclude_binaries=True,
    name='ExpedienteExtractor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ExpedienteExtractor',
)
