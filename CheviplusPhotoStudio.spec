
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets"), ("models", "models")]
binaries = []
hiddenimports = []

for package in ("rembg", "onnxruntime", "pymatting"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["app.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Cheviplus Photo Studio",
    console=False,
    upx=False,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    name="Cheviplus Photo Studio",
    upx=False,
)
