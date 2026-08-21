"""通用辅助函数."""

from __future__ import annotations

from pathlib import Path

from .constants import EXTENSION_MAP, LOSSLESS_CODECS


def codec_category(codec_name: str) -> str:
    name = (codec_name or "").lower()
    if name in LOSSLESS_CODECS or name.startswith("pcm_"):
        return "lossless"
    return "lossy"


def suggested_extension(codec_name: str, convert_to_mp3: bool = False) -> str:
    if convert_to_mp3:
        return ".mp3"
    name = (codec_name or "").lower()
    if name.startswith("pcm_"):
        return ".wav"
    return EXTENSION_MAP.get(name, ".mka")


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 0:
        return "未知"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size_bytes} B"


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--:--"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_bitrate(bit_rate: int | None) -> str:
    if not bit_rate:
        return "可变码率"
    if bit_rate >= 1_000_000:
        return f"{bit_rate / 1_000_000:.1f} Mbps"
    return f"{bit_rate // 1000} kbps"


def channel_layout_display(channels: int, layout: str | None) -> str:
    layout_map = {
        "mono": "单声道",
        "stereo": "立体声",
        "5.1": "5.1声道",
        "5.1(side)": "5.1声道",
        "7.1": "7.1声道",
        "7.1(wide)": "7.1声道",
        "quad": "四声道",
    }
    if layout:
        key = layout.lower()
        if key in layout_map:
            return layout_map[key]
        if layout in layout_map:
            return layout_map[layout]
    if channels == 1:
        return "单声道"
    if channels == 2:
        return "立体声"
    if channels == 6:
        return "5.1声道"
    if channels == 8:
        return "7.1声道"
    return f"{channels}声道"


def language_display(language: str | None) -> str:
    if not language or language.lower() in {"und", "unknown", "null"}:
        return "未知"
    return language


def resolve_output_conflict(path: Path, strategy: str = "rename") -> Path | None:
    """处理输出文件名冲突。

    strategy:
      - rename: 自动追加 (1)/(2)...
      - overwrite: 直接返回原路径
      - skip: 已存在则返回 None
    """
    if not path.exists():
        return path
    if strategy == "overwrite":
        return path
    if strategy == "skip":
        return None

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1
