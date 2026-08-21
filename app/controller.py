"""应用控制器：调度解析与提取任务."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QMessageBox

from app.core import Extractor, FFmpegManager, FolderScanner, ParseError, Parser
from app.models import (
    AppState,
    AudioTrackInfo,
    ExportOptions,
    ExtractStatus,
    ExtractTask,
    VideoFileInfo,
)
from app.utils.constants import DEFAULT_FFMPEG_CONCURRENCY, MAX_BATCH_FILES, MAX_PARSE_WORKERS


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str, str)  # path, message
    progress = Signal(object)
    status = Signal(str)


class ParseWorker(QRunnable):
    def __init__(self, parser: Parser, file_path: str) -> None:
        super().__init__()
        self.parser = parser
        self.file_path = file_path
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            info = self.parser.parse(self.file_path)
            self.signals.finished.emit(info)
        except ParseError as exc:
            self.signals.error.emit(self.file_path, exc.message)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(self.file_path, str(exc))


class ExtractWorker(QRunnable):
    def __init__(self, extractor: Extractor, tasks: list[ExtractTask]) -> None:
        super().__init__()
        self.extractor = extractor
        self.tasks = tasks
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        total = len(self.tasks)
        completed = 0
        results: list[ExtractTask] = []
        for task in self.tasks:
            def _cb(t: ExtractTask, _completed=completed, _total=total) -> None:
                overall = (_completed * 100.0 + t.progress) / max(_total, 1)
                self.signals.progress.emit({"task": t, "overall": overall})

            result = self.extractor.run_task(task, progress_cb=_cb)
            results.append(result)
            completed += 1
            overall = completed * 100.0 / max(total, 1)
            self.signals.progress.emit({"task": result, "overall": overall})
            if result.status == ExtractStatus.CANCELLED:
                break
        self.signals.finished.emit(results)


class BatchExtractWorker(QRunnable):
    """按并发限制执行批量提取任务."""

    def __init__(
        self,
        ffmpeg: FFmpegManager,
        tasks: list[ExtractTask],
        concurrency: int = DEFAULT_FFMPEG_CONCURRENCY,
    ) -> None:
        super().__init__()
        self.ffmpeg = ffmpeg
        self.tasks = tasks
        self.concurrency = max(1, concurrency)
        self.signals = WorkerSignals()
        self._cancelled = False
        self._extractors: list[Extractor] = []

    def cancel(self) -> None:
        self._cancelled = True
        for ext in self._extractors:
            ext.cancel()
        self.ffmpeg.terminate_all()

    @Slot()
    def run(self) -> None:
        total = len(self.tasks)
        completed = 0
        results: list[ExtractTask] = []
        lock_progress = {"completed": 0}

        def run_one(task: ExtractTask) -> ExtractTask:
            if self._cancelled:
                task.status = ExtractStatus.CANCELLED
                return task
            extractor = Extractor(self.ffmpeg)
            self._extractors.append(extractor)

            def _cb(t: ExtractTask) -> None:
                overall = (lock_progress["completed"] * 100.0 + t.progress / max(total, 1))
                # rough overall; refined after each completion
                self.signals.progress.emit({"task": t, "overall": min(99.0, overall)})

            return extractor.run_task(task, progress_cb=_cb)

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = []
            for task in self.tasks:
                if self._cancelled:
                    break
                futures.append(pool.submit(run_one, task))
            for future in futures:
                result = future.result()
                results.append(result)
                completed += 1
                lock_progress["completed"] = completed
                overall = completed * 100.0 / max(total, 1)
                self.signals.progress.emit({"task": result, "overall": overall})

        self.signals.finished.emit(results)


class AppController(QObject):
    status_message = Signal(str)
    single_parsed = Signal(object)
    single_parse_failed = Signal(str)
    batch_parsed = Signal(object)
    batch_parse_failed = Signal(str, str)
    batch_parse_progress = Signal(int, int)
    extract_progress = Signal(float)
    extract_task_progress = Signal(object)
    extract_finished = Signal(list)
    state_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ffmpeg = FFmpegManager()
        self.parser = Parser(self.ffmpeg)
        self.extractor = Extractor(self.ffmpeg)
        self.scanner = FolderScanner(max_files=MAX_BATCH_FILES)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(DEFAULT_FFMPEG_CONCURRENCY, MAX_PARSE_WORKERS))
        self.state = AppState.IDLE
        self._batch_parse_total = 0
        self._batch_parse_done = 0
        self._batch_worker: BatchExtractWorker | None = None
        self._extract_worker: ExtractWorker | None = None

    def ffmpeg_status_text(self) -> str:
        if not self.ffmpeg.available:
            return "FFmpeg 不可用"
        text = f"FFmpeg {self.ffmpeg.info.version}"
        if not self.ffmpeg.has_libmp3lame:
            text += " (无 libmp3lame)"
        return text

    def set_state(self, state: AppState) -> None:
        self.state = state
        self.state_changed.emit(state)

    def parse_single(self, file_path: str) -> None:
        if not self.ffmpeg.available:
            self.status_message.emit(self.ffmpeg.info.error_message or "FFmpeg 不可用")
            return
        self.set_state(AppState.PARSING)
        self.status_message.emit("正在解析文件…")
        worker = ParseWorker(self.parser, file_path)
        worker.signals.finished.connect(self._on_single_parsed)
        worker.signals.error.connect(self._on_single_parse_error)
        self.pool.start(worker)

    def _on_single_parsed(self, info: VideoFileInfo) -> None:
        self.set_state(AppState.READY)
        self.status_message.emit("解析完成")
        self.single_parsed.emit(info)

    def _on_single_parse_error(self, _path: str, message: str) -> None:
        self.set_state(AppState.ERROR)
        self.status_message.emit(f"错误: {message}")
        self.single_parse_failed.emit(message)

    def collect_batch_paths(
        self, raw_paths: list[str], existing: set[str]
    ) -> tuple[list[str], str | None]:
        collected, truncated, raw_count = self.scanner.collect_paths(raw_paths, existing)
        message = None
        if not collected:
            message = "在所选路径中未检测到任何视频文件"
        elif truncated:
            message = (
                f"检测到超过 {MAX_BATCH_FILES} 个视频文件，已截取前 {MAX_BATCH_FILES} 个"
            )
        elif raw_count and len(collected) < raw_count:
            message = f"已忽略重复文件，新增 {len(collected)} 个"
        return collected, message

    def parse_batch(self, file_paths: list[str]) -> None:
        if not self.ffmpeg.available:
            self.status_message.emit(self.ffmpeg.info.error_message or "FFmpeg 不可用")
            return
        self.set_state(AppState.PARSING)
        self._batch_parse_total = len(file_paths)
        self._batch_parse_done = 0
        self.status_message.emit(f"正在解析 (0/{self._batch_parse_total})…")
        for path in file_paths:
            worker = ParseWorker(self.parser, path)
            worker.signals.finished.connect(self._on_batch_parsed)
            worker.signals.error.connect(self._on_batch_parse_error)
            self.pool.start(worker)

    def _on_batch_parsed(self, info: VideoFileInfo) -> None:
        self._batch_parse_done += 1
        self.batch_parsed.emit(info)
        self.batch_parse_progress.emit(self._batch_parse_done, self._batch_parse_total)
        self.status_message.emit(
            f"正在解析 ({self._batch_parse_done}/{self._batch_parse_total})…"
        )
        if self._batch_parse_done >= self._batch_parse_total:
            self.set_state(AppState.READY)
            self.status_message.emit("批量解析完成")

    def _on_batch_parse_error(self, path: str, message: str) -> None:
        self._batch_parse_done += 1
        self.batch_parse_failed.emit(path, message)
        self.batch_parse_progress.emit(self._batch_parse_done, self._batch_parse_total)
        if self._batch_parse_done >= self._batch_parse_total:
            self.set_state(AppState.READY)
            self.status_message.emit("批量解析完成（部分失败）")

    def build_tasks_for_video(
        self,
        video: VideoFileInfo,
        tracks: list[AudioTrackInfo],
        options: ExportOptions,
        *,
        batch_subdir: bool = False,
    ) -> list[ExtractTask]:
        assert options.output_directory
        if batch_subdir:
            out_dir = str(Path(options.output_directory) / f"{Path(video.file_name).stem}_audio")
        else:
            out_dir = options.output_directory

        tasks: list[ExtractTask] = []
        for track in tracks:
            tasks.append(self.extractor.build_audio_task(video, track, options, out_dir))

        if options.export_video_only and video.has_video:
            # 纯视频放在输出目录根下（批量）或同一目录（单视频）
            video_out = options.output_directory if batch_subdir else out_dir
            video_task = self.extractor.build_video_only_task(video, video_out)
            if video_task:
                tasks.append(video_task)
        return tasks

    def start_extract(self, tasks: list[ExtractTask], batch: bool = False) -> None:
        if not tasks:
            self.status_message.emit("没有可执行的任务")
            return
        if not self.ffmpeg.available:
            self.status_message.emit(self.ffmpeg.info.error_message or "FFmpeg 不可用")
            return

        self.extractor.reset_cancel()
        self.set_state(AppState.EXTRACTING)
        self.status_message.emit(f"正在提取 (0/{len(tasks)})…")

        if batch:
            worker = BatchExtractWorker(self.ffmpeg, tasks)
            self._batch_worker = worker
            worker.signals.progress.connect(self._on_extract_progress)
            worker.signals.finished.connect(self._on_extract_finished)
            self.pool.start(worker)
        else:
            worker = ExtractWorker(self.extractor, tasks)
            self._extract_worker = worker
            worker.signals.progress.connect(self._on_extract_progress)
            worker.signals.finished.connect(self._on_extract_finished)
            self.pool.start(worker)

    def cancel_extract(self) -> None:
        self.extractor.cancel()
        if self._batch_worker:
            self._batch_worker.cancel()
        self.status_message.emit("正在取消…")

    def shutdown(self) -> None:
        """关闭本工具窗口时停止本实例任务，不影响其他工具窗口。"""
        self.extractor.cancel()
        if self._batch_worker:
            self._batch_worker.cancel()
        self.pool.clear()
        self.pool.waitForDone(5000)

    def _on_extract_progress(self, payload: dict) -> None:
        overall = float(payload.get("overall") or 0)
        task = payload.get("task")
        self.extract_progress.emit(overall)
        if task:
            self.extract_task_progress.emit(task)
            if isinstance(task, ExtractTask) and task.track is not None:
                self.status_message.emit(
                    f"正在提取音轨 #{task.track.index + 1}… ({overall:.0f}%)"
                )
            elif isinstance(task, ExtractTask):
                self.status_message.emit(f"正在导出纯视频… ({overall:.0f}%)")

    def _on_extract_finished(self, results: list) -> None:
        self._batch_worker = None
        self._extract_worker = None
        success = sum(1 for t in results if t.status == ExtractStatus.COMPLETED)
        failed = sum(1 for t in results if t.status == ExtractStatus.FAILED)
        cancelled = sum(1 for t in results if t.status == ExtractStatus.CANCELLED)
        self.set_state(AppState.DONE if not cancelled else AppState.READY)
        if cancelled:
            self.status_message.emit(f"提取已取消，已完成 {success} 个文件")
        else:
            self.status_message.emit(
                f"提取完成，成功 {success}，失败 {failed}，共 {len(results)} 个任务"
            )
        self.extract_finished.emit(results)

    def ensure_output_dir(self, options: ExportOptions, parent_widget) -> bool:
        if not options.output_directory:
            QMessageBox.warning(parent_widget, "提示", "请先选择导出目录")
            return False
        path = Path(options.output_directory)
        if not path.exists() or not path.is_dir():
            QMessageBox.warning(parent_widget, "提示", "导出目录无效，请重新选择")
            return False
        if not self.ffmpeg.check_writable(str(path)):
            QMessageBox.warning(
                parent_widget, "提示", "无法写入到所选目录，请选择其他输出位置"
            )
            return False
        return True
