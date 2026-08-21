"""纯视频导出与音轨提取."""

from __future__ import annotations

import re
import time
from pathlib import Path

from app.models import (
    AudioTrackInfo,
    ExportOptions,
    ExtractStatus,
    ExtractTask,
    ExtractType,
    VideoFileInfo,
)
from app.utils.constants import DEFAULT_MP3_BITRATE
from app.utils.helpers import resolve_output_conflict, suggested_extension

from .ffmpeg_manager import FFmpegManager

TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


class Extractor:
    def __init__(self, ffmpeg: FFmpegManager, conflict_strategy: str = "rename") -> None:
        self._ffmpeg = ffmpeg
        self.conflict_strategy = conflict_strategy
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self._ffmpeg.terminate_all()

    def reset_cancel(self) -> None:
        self._cancelled = False

    def build_audio_task(
        self,
        video: VideoFileInfo,
        track: AudioTrackInfo,
        options: ExportOptions,
        output_dir: str,
    ) -> ExtractTask:
        convert_mp3 = options.convert_to_mp3
        ext = suggested_extension(track.codec_name, convert_to_mp3=convert_mp3)
        lang = track.language or "und"
        base_name = f"{Path(video.file_name).stem}_track{track.index + 1}_{lang}{ext}"
        output_path = Path(output_dir) / base_name
        resolved = resolve_output_conflict(output_path, self.conflict_strategy)
        if resolved is None:
            task = ExtractTask(
                task_type=ExtractType.MP3_CONVERT if convert_mp3 else ExtractType.AUDIO_EXTRACT,
                source_file=video.file_path,
                track=track,
                output_dir=output_dir,
                output_path="",
                status=ExtractStatus.CANCELLED,
                error_message="输出文件已存在，已跳过",
                duration_hint=track.duration or video.duration,
            )
            return task

        if convert_mp3:
            bitrate = options.mp3_bitrate or DEFAULT_MP3_BITRATE
            cmd = [
                "-y",
                "-i",
                video.file_path,
                "-map",
                f"0:a:{track.index}",
                "-c:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                str(resolved),
            ]
            task_type = ExtractType.MP3_CONVERT
        else:
            cmd = [
                "-y",
                "-i",
                video.file_path,
                "-map",
                f"0:a:{track.index}",
                "-c",
                "copy",
                str(resolved),
            ]
            task_type = ExtractType.AUDIO_EXTRACT

        return ExtractTask(
            task_type=task_type,
            source_file=video.file_path,
            track=track,
            output_dir=output_dir,
            output_path=str(resolved),
            ffmpeg_command=cmd,
            duration_hint=track.duration or video.duration,
        )

    def build_video_only_task(
        self,
        video: VideoFileInfo,
        output_dir: str,
    ) -> ExtractTask | None:
        if not video.has_video:
            return None
        stem = Path(video.file_name).stem
        ext = Path(video.file_name).suffix or ".mp4"
        output_path = Path(output_dir) / f"{stem}_no_audio{ext}"
        resolved = resolve_output_conflict(output_path, self.conflict_strategy)
        if resolved is None:
            return ExtractTask(
                task_type=ExtractType.VIDEO_ONLY_EXPORT,
                source_file=video.file_path,
                track=None,
                output_dir=output_dir,
                output_path="",
                status=ExtractStatus.CANCELLED,
                error_message="输出文件已存在，已跳过",
                duration_hint=video.duration,
            )

        cmd = [
            "-y",
            "-i",
            video.file_path,
            "-map",
            "0:v",
            "-c",
            "copy",
            "-an",
            str(resolved),
        ]
        return ExtractTask(
            task_type=ExtractType.VIDEO_ONLY_EXPORT,
            source_file=video.file_path,
            track=None,
            output_dir=output_dir,
            output_path=str(resolved),
            ffmpeg_command=cmd,
            duration_hint=video.duration,
        )

    def run_task(self, task: ExtractTask, progress_cb=None) -> ExtractTask:
        if self._cancelled:
            task.status = ExtractStatus.CANCELLED
            return task
        if task.status == ExtractStatus.CANCELLED:
            return task
        if not task.ffmpeg_command:
            task.status = ExtractStatus.FAILED
            task.error_message = task.error_message or "无效的提取任务"
            return task

        Path(task.output_dir).mkdir(parents=True, exist_ok=True)
        task.status = ExtractStatus.RUNNING
        task.start_time = time.time()
        task.progress = 0.0

        process = None
        try:
            process = self._ffmpeg.popen_ffmpeg(task.ffmpeg_command)
            assert process.stderr is not None
            for line in process.stderr:
                if self._cancelled:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except Exception:  # noqa: BLE001
                        process.kill()
                    task.status = ExtractStatus.CANCELLED
                    self._cleanup_partial(task)
                    return task

                progress = self._parse_progress(line, task.duration_hint)
                if progress is not None:
                    task.progress = progress
                    if progress_cb:
                        progress_cb(task)

            return_code = process.wait()
            task.end_time = time.time()
            if return_code == 0:
                task.progress = 100.0
                task.status = ExtractStatus.COMPLETED
            else:
                task.status = ExtractStatus.FAILED
                task.error_message = f"FFmpeg 退出码 {return_code}"
                self._cleanup_partial(task)
        except Exception as exc:  # noqa: BLE001
            task.status = ExtractStatus.FAILED
            task.error_message = str(exc)
            task.end_time = time.time()
            self._cleanup_partial(task)
        finally:
            if process is not None:
                self._ffmpeg.unregister(process)
            if progress_cb:
                progress_cb(task)
        return task

    @staticmethod
    def _parse_progress(line: str, duration: float | None) -> float | None:
        match = TIME_RE.search(line)
        if not match or not duration or duration <= 0:
            return None
        hours, minutes, seconds = match.groups()
        current = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return max(0.0, min(99.0, current / duration * 100.0))

    @staticmethod
    def _cleanup_partial(task: ExtractTask) -> None:
        if not task.output_path:
            return
        path = Path(task.output_path)
        if path.exists() and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass


class VideoExporter:
    """纯视频导出辅助（命令构建委托给 Extractor）."""

    def __init__(self, extractor: Extractor) -> None:
        self._extractor = extractor

    def build_task(self, video: VideoFileInfo, output_dir: str) -> ExtractTask | None:
        return self._extractor.build_video_only_task(video, output_dir)
