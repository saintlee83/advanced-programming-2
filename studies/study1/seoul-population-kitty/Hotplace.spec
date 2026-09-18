"""Build from this directory: uv run --with 'pyinstaller>=6.16,<7' pyinstaller --noconfirm Hotplace.spec

Outputs go to ./build and ./dist next to this file.
macOS 에서는 dist/HotplaceKitty.app, Windows 에서는 dist/HotplaceKitty/HotplaceKitty.exe 가 만들어진다.
PyInstaller 는 실행한 운영체제용으로만 빌드한다 (Windows 용은 .github/workflows/windows-build.yml).
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
macos = sys.platform == "darwin"
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
    target_arch="arm64" if macos else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="HotplaceKitty", strip=False, upx=False)
if macos:
    app = BUNDLE(
        coll, name="HotplaceKitty.app", bundle_identifier="com.hotplace.kitty",
        info_plist={"CFBundleDisplayName": "서울 생활인구 비교 · Kitty", "NSHighResolutionCapable": True,
                    "CFBundleShortVersionString": "0.1.0"},
    )
