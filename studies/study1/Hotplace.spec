"""Build with: uv run --with pyinstaller pyinstaller studies/study1/Hotplace.spec

Use --distpath studies/study1/dist --workpath studies/study1/build from the repo root.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
a = Analysis(
    [str(root / "app.py")],
    pathex=[str(root)],
    binaries=[],
    datas=collect_data_files("qfluentwidgets") + [(str(root / "hotplace/assets"), "hotplace/assets")],
    hiddenimports=["PySide6.QtSvg"],
    hooksconfig={"matplotlib": {"backends": ["QtAgg", "Agg"]}},
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="Hotplace", console=False, debug=False, strip=False, upx=False,
    target_arch="arm64",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Hotplace", strip=False, upx=False)
app = BUNDLE(
    coll, name="Hotplace.app", bundle_identifier="com.hotplace.analyzer",
    info_plist={"CFBundleDisplayName": "서울 생활인구 비교", "NSHighResolutionCapable": True,
                "CFBundleShortVersionString": "0.1.0"},
)
