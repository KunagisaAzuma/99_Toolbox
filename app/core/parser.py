"""视频解析模块（ffprobe）."""

from __future__ import annotations

import json
from pathlib import Path

from app.models import AudioTrackInfo, ParseStatus, VideoFileInfo
from app.utils.helpers import codec_category, suggested_extension

from .ffmpeg_manager import FFmpegManager


class ParseError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Parser:
    def __init__(self, ffmpeg: FFmpegManager) -> None:
        self._ffmpeg = ffmpeg

    def parse(self, file_path: str) -> VideoFileInfo:
        path = Path(file_path).resolve()
        if not path.exists():
            raise ParseError("文件已被移动或删除，请重新选择")
        if not path.is_file():
            raise ParseError("所选路径不是有效的视频文件")
        if not os_access_readable(path):
            raise ParseError("无权限读取该文件")

        if not self._ffmpeg.available:
            raise ParseError(self._ffmpeg.info.error_message or "FFmpeg 不可用")

        try:
            result = self._ffmpeg.run_ffprobe(
                [
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_streams",
                    "-show_format",
                    str(path),
                ]
            )
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"无法解析该文件：{exc}") from exc

        if result.returncode != 0:
            raise ParseError("无法解析该文件，文件可能已损坏或不是有效的视频文件")

        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ParseError("无法解析该文件，元数据格式异常") from exc

        return self._build_video_info(path, data)

    def _build_video_info(self, path: Path, data: dict) -> VideoFileInfo:
        fmt = data.get("format") or {}
        streams = data.get("streams") or []

        duration = _to_float(fmt.get("duration")) or 0.0
        total_bit_rate = _to_int(fmt.get("bit_rate"))
        tags = {str(k): str(v) for k, v in (fmt.get("tags") or {}).items()}

        audio_tracks: list[AudioTrackInfo] = []
        has_video = False
        video_codec: str | None = None
        audio_index = 0

        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type == "video" and not has_video:
                # 忽略封面图等 attached_pic
                disposition = stream.get("disposition") or {}
                if disposition.get("attached_pic"):
                    continue
                has_video = True
                video_codec = stream.get("codec_name")
            elif codec_type == "audio":
                track = self._build_audio_track(stream, audio_index, duration)
                audio_tracks.append(track)
                audio_index += 1

        try:
            file_size = path.stat().st_size
        except OSError:
            file_size = _to_int(fmt.get("size")) or 0

        return VideoFileInfo(
            file_path=str(path),
            file_name=path.name,
            file_size=file_size,
            duration=duration,
            format_name=fmt.get("format_name") or "",
            format_long_name=fmt.get("format_long_name") or "",
            audio_tracks=audio_tracks,
            has_video=has_video,
            video_codec=video_codec,
            total_bit_rate=total_bit_rate,
            tags=tags,
            parse_status=ParseStatus.SUCCESS,
        )

    def _build_audio_track(
        self, stream: dict, audio_index: int, fallback_duration: float
    ) -> AudioTrackInfo:
        codec_name = (stream.get("codec_name") or "unknown").lower()
        tags = {str(k): str(v) for k, v in (stream.get("tags") or {}).items()}
        language = tags.get("language")
        title = tags.get("title")
        duration = _to_float(stream.get("duration")) or fallback_duration or None

        return AudioTrackInfo(
            index=audio_index,
            codec_name=codec_name,
            codec_long_name=stream.get("codec_long_name") or codec_name,
            codec_category=codec_category(codec_name),
            channels=_to_int(stream.get("channels")) or 2,
            channel_layout=stream.get("channel_layout") or "",
            sample_rate=_to_int(stream.get("sample_rate")) or 0,
            bit_rate=_to_int(stream.get("bit_rate")),
            language=language,
            duration=duration,
            title=title,
            profile=stream.get("profile"),
            frames=_to_int(stream.get("nb_frames")),
            tags=tags,
            suggested_extension=suggested_extension(codec_name),
            default_selected=audio_index < 2,
        )


def os_access_readable(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            handle.read(1)
        return True
    except OSError:
        return False


def _to_int(value) -> int | None:
    if value is None or value == "N/A":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float | None:
    if value is None or value == "N/A":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
