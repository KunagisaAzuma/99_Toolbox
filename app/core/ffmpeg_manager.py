"""FFmpeg 进程与可用性管理."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.utils.constants import bundled_ffmpeg_bin_dir


@dataclass
class FFmpegInfo:
    available: bool = False
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    version: str = ""
    has_libmp3lame: bool = False
    bundled: bool = False
    error_message: str | None = None


class FFmpegManager:
    """定位并管理 ffmpeg / ffprobe 可执行文件.

    优先使用项目内置的 ffmpeg-8.1.2-essentials_build，打包后同样从此目录加载。
    """

    def __init__(self) -> None:
        self._info = FFmpegInfo()
        self._active_processes: list[subprocess.Popen] = []
        self.detect()

    @property
    def info(self) -> FFmpegInfo:
        return self._info

    @property
    def available(self) -> bool:
        return self._info.available

    @property
    def has_libmp3lame(self) -> bool:
        return self._info.has_libmp3lame

    def detect(self) -> FFmpegInfo:
        ffmpeg, from_bundle = self._resolve_binary("ffmpeg")
        ffprobe, _ = self._resolve_binary("ffprobe")
        if not ffmpeg or not ffprobe:
            self._info = FFmpegInfo(
                available=False,
                ffmpeg_path=ffmpeg,
                ffprobe_path=ffprobe,
                bundled=False,
                error_message=(
                    "未找到内置 FFmpeg（ffmpeg-8.1.2-essentials_build/bin），"
                    "请确认该目录已随软件分发"
                ),
            )
            return self._info

        version = self._query_version(ffmpeg)
        has_lame = self._check_libmp3lame(ffmpeg)
        self._info = FFmpegInfo(
            available=True,
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            version=version,
            has_libmp3lame=has_lame,
            bundled=from_bundle,
        )
        return self._info

    def _resolve_binary(self, name: str) -> tuple[str | None, bool]:
        exe_name = f"{name}.exe" if sys.platform == "win32" else name

        # 1. 内置目录（开发环境 / PyInstaller 打包后均优先）
        bundled = bundled_ffmpeg_bin_dir() / exe_name
        if bundled.exists():
            return str(bundled), True

        # 2. PyInstaller 扁平放置兼容
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            flat = Path(meipass) / exe_name
            if flat.exists():
                return str(flat), True

        # 3. 系统 PATH（仅作兜底）
        found = shutil.which(name) or (
            shutil.which(f"{name}.exe") if sys.platform == "win32" else None
        )
        if found:
            return found, False
        return None, False
    def _query_version(self, ffmpeg_path: str) -> str:
        try:
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                creationflags=self._creation_flags(),
            )
            first = (result.stdout or "").splitlines()
            if first:
                match = re.search(r"version\s+([\w.\-]+)", first[0])
                return match.group(1) if match else first[0].strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return "unknown"

    def _check_libmp3lame(self, ffmpeg_path: str) -> bool:
        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                creationflags=self._creation_flags(),
            )
            output = (result.stdout or "") + (result.stderr or "")
            return "libmp3lame" in output
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _creation_flags() -> int:
        if sys.platform == "win32":
            return getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return 0

    def run_ffprobe(self, args: list[str], timeout: float | None = 120) -> subprocess.CompletedProcess:
        if not self._info.ffprobe_path:
            raise RuntimeError("ffprobe 不可用")
        return subprocess.run(
            [self._info.ffprobe_path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=self._creation_flags(),
        )

    def popen_ffmpeg(self, args: list[str]) -> subprocess.Popen:
        if not self._info.ffmpeg_path:
            raise RuntimeError("ffmpeg 不可用")
        process = subprocess.Popen(
            [self._info.ffmpeg_path, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=self._creation_flags(),
        )
        self._active_processes.append(process)
        return process

    def unregister(self, process: subprocess.Popen) -> None:
        if process in self._active_processes:
            self._active_processes.remove(process)

    def terminate_all(self) -> None:
        for process in list(self._active_processes):
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
            except OSError:
                pass
            finally:
                self.unregister(process)

    def check_writable(self, directory: str) -> bool:
        path = Path(directory)
        if not path.exists() or not path.is_dir():
            return False
        test_file = path / f".flm_write_test_{os.getpid()}"
        try:
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return True
        except OSError:
            return False
