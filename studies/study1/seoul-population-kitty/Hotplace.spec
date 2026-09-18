"""Build from this directory: uv run --with 'pyinstaller>=6.16,<7' pyinstaller --noconfirm Hotplace.spec

Outputs go to ./build and ./dist next to this file.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
a = Analysis(
    [str(root / "app.py")],
    pathex=[str(root)],
    binaries=[],
    datas=collect_data_files("qfluentwidgets") + [(str(root / "hotplace" / "assets"), "hotplace/assets")],
    hiddenimports=["PyQt5.QtSvg"],
    hooksconfig={"matplotlib": {"backends": ["QtAgg", "Agg"]}},
    excludes=["PyQt6", "PySide2", "PySide6", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="HotplaceKitty", console=False, debug=False, strip=False, upx=False,
    target_arch="arm64",
)
coll = COLLECT(exe, a.binaries, a.datas, name="HotplaceKitty", strip=False, upx=False)
app = BUNDLE(
    coll, name="HotplaceKitty.app", bundle_identifier="com.hotplace.kitty",
    info_plist={"CFBundleDisplayName": "서울 생활인구 비교 · Kitty", "NSHighResolutionCapable": True,
                "CFBundleShortVersionString": "0.1.0"},
)
