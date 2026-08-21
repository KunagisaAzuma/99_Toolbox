"""主窗口."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.controller import AppController
from app.models import AppState, ExtractStatus, ExtractTask, VideoFileInfo
from app.ui import BatchProcessPage, SingleVideoPage
from app.utils.constants import (
    APP_AUTHOR_LINE,
    APP_ORG,
    EXTRACT_TOOL_NAME,
)


class ExtractToolWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(EXTRACT_TOOL_NAME)
        self.setWindowIcon(QIcon())  # 去掉标题栏默认图标
        self.resize(860, 640)

        self.settings = QSettings(APP_ORG, EXTRACT_TOOL_NAME)
        self.controller = AppController(self)

        self.tabs = QTabWidget()
        self.single_page = SingleVideoPage()
        self.batch_page = BatchProcessPage()
        self.tabs.addTab(self.single_page, "单视频处理")
        self.tabs.addTab(self.batch_page, "批量处理")

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.tabs, 1)

        self.author_label = QLabel(APP_AUTHOR_LINE)
        self.author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        central_layout.addWidget(self.author_label)
        self.setCentralWidget(central)
        self.menuBar().hide()

        self._build_status_bar()
        self._connect_signals()
        self._restore_state()
        self._apply_ffmpeg_status()

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)
        self.status_label = QLabel("就绪")
        bar.addWidget(self.status_label, 1)
        self.ffmpeg_label = QLabel("")
        bar.addPermanentWidget(self.ffmpeg_label)

    def _connect_signals(self) -> None:
        ctrl = self.controller

        self.single_page.file_selected.connect(ctrl.parse_single)
        self.single_page.clear_requested.connect(self._clear_single)
        self.single_page.extract_selected.connect(self._extract_single_selected)
        self.single_page.extract_all.connect(self._extract_single_all)
        self.single_page.cancel_requested.connect(self._cancel_extract)
        self.single_page.options_changed.connect(self._persist_output_dirs)

        self.batch_page.paths_selected.connect(self._on_batch_paths)
        self.batch_page.clear_requested.connect(self._clear_batch)
        self.batch_page.remove_file.connect(self.batch_page.remove_path)
        self.batch_page.extract_selected.connect(self._extract_batch_selected)
        self.batch_page.extract_all.connect(self._extract_batch_all)
        self.batch_page.cancel_requested.connect(self._cancel_extract)
        self.batch_page.options_changed.connect(self._persist_output_dirs)

        ctrl.status_message.connect(self.status_label.setText)
        ctrl.single_parsed.connect(self._on_single_parsed)
        ctrl.single_parse_failed.connect(self._on_single_parse_failed)
        ctrl.batch_parsed.connect(self.batch_page.on_parsed)
        ctrl.batch_parse_failed.connect(self.batch_page.on_parse_failed)
        ctrl.batch_parse_progress.connect(self.batch_page.set_parse_progress)
        ctrl.extract_progress.connect(self._on_extract_progress)
        ctrl.extract_task_progress.connect(self._on_extract_task_progress)
        ctrl.extract_finished.connect(self._on_extract_finished)
        ctrl.state_changed.connect(self._on_state_changed)

    def _apply_ffmpeg_status(self) -> None:
        info = self.controller.ffmpeg.info
        text = self.controller.ffmpeg_status_text()
        if info.available and info.bundled:
            text = f"内置 {text}"
        self.ffmpeg_label.setText(text)
        if not self.controller.ffmpeg.available:
            self.status_label.setText(
                self.controller.ffmpeg.info.error_message or "FFmpeg 不可用"
            )

        available = self.controller.ffmpeg.has_libmp3lame
        self.single_page.set_mp3_available(available and self.controller.ffmpeg.available)
        self.batch_page.set_mp3_available(available and self.controller.ffmpeg.available)

    def _default_output_dir(self) -> str:
        saved = self.settings.value("output_directory", "", type=str)
        if saved and Path(saved).is_dir():
            return saved
        music = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)
        return music or str(Path.home())

    def _restore_state(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        tab = self.settings.value("active_tab", 0, type=int)
        self.tabs.setCurrentIndex(tab)
        out = self._default_output_dir()
        self.single_page.set_default_output_dir(out)
        self.batch_page.set_default_output_dir(out)

    def _persist_output_dirs(self) -> None:
        single_dir = self.single_page.export_options.output_directory()
        batch_dir = self.batch_page.export_options.output_directory()
        for path in (single_dir, batch_dir):
            if path:
                self.settings.setValue("output_directory", path)
                break

    def closeEvent(self, event) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("active_tab", self.tabs.currentIndex())
        self._persist_output_dirs()
        self.controller.shutdown()
        super().closeEvent(event)

    def _clear_single(self) -> None:
        self.single_page.clear()
        self.controller.set_state(AppState.IDLE)
        self.status_label.setText("就绪")

    def _clear_batch(self) -> None:
        self.batch_page.clear()
        self.controller.set_state(AppState.IDLE)
        self.status_label.setText("就绪")

    def _on_single_parsed(self, info: VideoFileInfo) -> None:
        self.single_page.show_video(info)
        if not info.audio_tracks:
            self.status_label.setText("该视频不包含任何音频轨道")

    def _on_single_parse_failed(self, message: str) -> None:
        QMessageBox.warning(self, "解析失败", message)

    def _on_batch_paths(self, raw_paths: list[str]) -> None:
        existing = self.batch_page.existing_paths()
        collected, message = self.controller.collect_batch_paths(raw_paths, existing)
        if message and not collected:
            QMessageBox.information(self, "提示", message)
            return
        if message and collected:
            QMessageBox.information(self, "提示", message)
        duplicates = [p for p in collected if p in existing]
        new_paths = [p for p in collected if p not in existing]
        if duplicates and not new_paths:
            QMessageBox.information(self, "提示", "这些文件已在列表中，已忽略重复项")
            return
        if not new_paths:
            return
        self.batch_page.begin_files(new_paths)
        self.controller.parse_batch(new_paths)

    def _extract_single_selected(self) -> None:
        video = self.single_page.video
        if not video:
            return
        options = self.single_page.get_export_options()
        if not self.controller.ensure_output_dir(options, self):
            return
        tracks = self.single_page.selected_tracks()
        if not tracks and not options.export_video_only:
            QMessageBox.information(self, "提示", "请至少勾选一条音轨，或勾选导出纯视频")
            return
        tasks = self.controller.build_tasks_for_video(video, tracks, options)
        self._begin_extract(tasks, batch=False)

    def _extract_single_all(self) -> None:
        video = self.single_page.video
        if not video:
            return
        options = self.single_page.get_export_options()
        if not self.controller.ensure_output_dir(options, self):
            return
        tracks = self.single_page.all_tracks()
        tasks = self.controller.build_tasks_for_video(video, tracks, options)
        self._begin_extract(tasks, batch=False)

    def _extract_batch_selected(self) -> None:
        options = self.batch_page.get_export_options()
        if not self.controller.ensure_output_dir(options, self):
            return
        selected_map = self.batch_page.selected_by_file()
        videos = {v.file_path: v for v in self.batch_page.successful_videos()}
        tasks: list[ExtractTask] = []
        for path, tracks in selected_map.items():
            video = videos.get(path)
            if not video:
                continue
            if not tracks and not options.export_video_only:
                continue
            tasks.extend(
                self.controller.build_tasks_for_video(
                    video, tracks, options, batch_subdir=True
                )
            )
        if not tasks:
            QMessageBox.information(self, "提示", "请至少勾选一条音轨，或勾选导出纯视频")
            return
        self._begin_extract(tasks, batch=True)

    def _extract_batch_all(self) -> None:
        options = self.batch_page.get_export_options()
        if not self.controller.ensure_output_dir(options, self):
            return
        all_map = self.batch_page.all_tracks_by_file()
        videos = {v.file_path: v for v in self.batch_page.successful_videos()}
        tasks: list[ExtractTask] = []
        for path, tracks in all_map.items():
            video = videos.get(path)
            if not video:
                continue
            tasks.extend(
                self.controller.build_tasks_for_video(
                    video, tracks, options, batch_subdir=True
                )
            )
        if not tasks:
            QMessageBox.information(self, "提示", "没有可提取的音轨")
            return
        self._begin_extract(tasks, batch=True)

    def _begin_extract(self, tasks: list[ExtractTask], batch: bool) -> None:
        self._persist_output_dirs()
        self.single_page.set_extracting(True)
        self.batch_page.set_extracting(True)
        self._active_batch = batch
        self.controller.start_extract(tasks, batch=batch)

    def _cancel_extract(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认取消",
            "确定要取消当前提取任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.controller.cancel_extract()

    def _on_extract_progress(self, value: float) -> None:
        self.single_page.set_progress(value)
        self.batch_page.set_progress(value)

    def _on_extract_task_progress(self, task: ExtractTask) -> None:
        if getattr(self, "_active_batch", False):
            # 简单按源文件更新分组状态
            self.batch_page.mark_group_extracting(task.source_file, 0, 0)

    def _on_extract_finished(self, results: list) -> None:
        self.single_page.set_extracting(False)
        self.batch_page.set_extracting(False)
        self.single_page._refresh_actions()
        self.batch_page._refresh_actions()

        success = sum(1 for t in results if t.status == ExtractStatus.COMPLETED)
        failed = sum(1 for t in results if t.status == ExtractStatus.FAILED)
        cancelled = sum(1 for t in results if t.status == ExtractStatus.CANCELLED)

        if getattr(self, "_active_batch", False):
            by_file: dict[str, list] = {}
            for task in results:
                by_file.setdefault(task.source_file, []).append(task)
            for path, tasks in by_file.items():
                ok = all(t.status == ExtractStatus.COMPLETED for t in tasks)
                self.batch_page.mark_group_done(path, ok)

            box = QMessageBox(self)
            box.setWindowTitle("处理完成")
            box.setText(
                f"处理完成！成功: {success}, 失败: {failed}, 总任务数: {len(results)}"
                + ("（已取消）" if cancelled else "")
            )
            open_btn = box.addButton("打开输出文件夹", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == open_btn:
                out = self.batch_page.export_options.output_directory()
                if out:
                    self._open_folder(out)
        else:
            if failed and not cancelled:
                errors = "\n".join(
                    t.error_message or "未知错误"
                    for t in results
                    if t.status == ExtractStatus.FAILED
                )
                QMessageBox.warning(self, "部分失败", f"有任务失败：\n{errors}")
            elif success and not cancelled:
                reply = QMessageBox.question(
                    self,
                    "提取完成",
                    f"提取完成，共 {success} 个文件。\n是否打开输出文件夹？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    out = self.single_page.export_options.output_directory()
                    if out:
                        self._open_folder(out)

    def _on_state_changed(self, state: AppState) -> None:
        if state == AppState.IDLE:
            pass

    @staticmethod
    def _open_folder(path: str) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
