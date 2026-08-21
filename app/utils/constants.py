"""全局常量与映射表."""

from __future__ import annotations

from pathlib import Path

APP_NAME = "工具箱"
APP_ORG = "FLM"
APP_VERSION = "0.0.1"
EXTRACT_TOOL_NAME = "音视频分离工具"
DEPTH_TOOL_NAME = "深度图生成"
APP_AUTHOR = "玖渚東"
APP_AUTHOR_EN = "KunagisaAzuma"
APP_AUTHOR_LINE = f"v{APP_VERSION}  {APP_AUTHOR}，{APP_AUTHOR_EN}"

# 内置 FFmpeg（随项目/打包分发，优先于系统 PATH）
BUNDLED_FFMPEG_DIRNAME = "ffmpeg-8.1.2-essentials_build"
BUNDLED_ARIA2_DIRNAME = "aria2"

MAX_BATCH_FILES = 100
DEFAULT_MP3_BITRATE = "192k"
DEFAULT_FFMPEG_CONCURRENCY = 2
MAX_PARSE_WORKERS = 8


def project_root() -> Path:
    """项目根目录（开发环境）或打包解压目录."""
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def bundled_ffmpeg_bin_dir() -> Path:
    return project_root() / BUNDLED_FFMPEG_DIRNAME / "bin"


def bundled_aria2_dir() -> Path:
    return project_root() / BUNDLED_ARIA2_DIRNAME


LOSSLESS_CODECS = frozenset(
    {
        "flac",
        "alac",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "pcm_f32le",
        "truehd",
        "wavpack",
        "tta",
        "ape",
        "mlp",
    }
)

EXTENSION_MAP: dict[str, str] = {
    "aac": ".aac",
    "mp3": ".mp3",
    "flac": ".flac",
    "opus": ".opus",
    "vorbis": ".ogg",
    "dts": ".dts",
    "ac3": ".ac3",
    "eac3": ".eac3",
    "alac": ".m4a",
    "truehd": ".thd",
    "wavpack": ".wv",
    "tta": ".tta",
}

VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".ts",
        ".m4v",
        ".mts",
        ".m2ts",
        ".ogv",
        ".vob",
        ".3gp",
        ".asf",
        ".rmvb",
        ".divx",
    }
)

VIDEO_FILE_FILTER = (
    "视频文件 ("
    "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm "
    "*.ts *.m4v *.mts *.m2ts *.ogv *.vob *.3gp "
    "*.asf *.rmvb *.divx"
    ");;所有文件 (*.*)"
)

IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
)

IMAGE_FILE_FILTER = (
    "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff);;所有文件 (*.*)"
)
