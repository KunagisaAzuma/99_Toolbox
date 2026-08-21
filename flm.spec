# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 单文件打包：exe 内嵌 FFmpeg 与 aria2。"""

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

ffmpeg_bin = root / "ffmpeg-8.1.2-essentials_build" / "bin"
aria2_exe = root / "aria2" / "aria2c.exe"
aria2_copying = root / "aria2" / "COPYING"
binaries = [
    (str(ffmpeg_bin / "ffmpeg.exe"), "ffmpeg-8.1.2-essentials_build/bin"),
    (str(ffmpeg_bin / "ffprobe.exe"), "ffmpeg-8.1.2-essentials_build/bin"),
]
if aria2_exe.is_file():
    binaries.append((str(aria2_exe), "aria2"))
datas = []
if aria2_copying.is_file():
    datas.append((str(aria2_copying), "aria2"))

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["cv2", "onnxruntime", "numpy"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="工具箱",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
