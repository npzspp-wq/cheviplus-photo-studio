# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("assets", "assets"), ("models", "models")]
binaries = []
hiddenimports = []

for package in (
    "rembg", "onnxruntime", "pymatting", "numpy", "scipy",
    "skimage", "imageio", "pywt", "networkx", "pooch"
):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("scipy")
hiddenimports += collect_submodules("skimage")
hiddenimports += [
    "scipy._lib",
    "scipy._lib.messagestream",
    "scipy.linalg.cython_blas",
    "scipy.linalg.cython_lapack",
    "scipy.special._ufuncs_cxx",
    "scipy.spatial.transform._rotation_groups",
    "skimage.filters.rank.core_cy",
    "skimage.morphology._skeletonize_cy",
]

a = Analysis(
    ["launcher.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "tensorflow"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cheviplus Photo Studio",
    console=False,
    upx=False,
    icon="assets/app_icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="Cheviplus Photo Studio",
    upx=False,
)
