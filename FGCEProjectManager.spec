# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# Ensure we can find packages in venv
venv_path = os.path.join(os.getcwd(), '.venv')
if os.path.exists(venv_path):
    # Add site-packages to sys.path
    site_packages = os.path.join(venv_path, 'Lib', 'site-packages')
    if not os.path.exists(site_packages):
        site_packages = os.path.join(venv_path, 'lib', 'site-packages')
        if not os.path.exists(site_packages):
             site_packages = os.path.join(venv_path, 'lib', 'python3.12', 'site-packages')
    
    if os.path.exists(site_packages) and site_packages not in sys.path:
        print(f"Adding {site_packages} to sys.path")
        sys.path.insert(0, site_packages)

datas = [('app/templates', 'app/templates'), ('app/static', 'app/static')]
binaries = []
hiddenimports = ['flask_sqlalchemy', 'flask_migrate', 'flask_wtf', 'dotenv']

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
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
    name='FGCEProjectManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='FGCEProjectManager',
)
