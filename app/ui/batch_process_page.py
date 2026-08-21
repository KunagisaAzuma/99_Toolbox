"""批量处理页面."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from app.models import ExportOptions, VideoFileInfo
from app.utils.constants import VIDEO_FILE_FILTER

from .action_bar import ActionBar
from .drop_zone import BatchDropZone
from .export_options_widget import ExportOptionsWidget
from .file_info_bar import FileSummaryBar
from .track_list import VideoFileGroupList


class BatchProcessPage(QWidget):
    paths_selected = Signal(list)
    clear_requested = Signal()
    remove_file = Signal(str)
    extract_selected = Signal()
    extract_all = Signal()
    cancel_requested = Signal()
    options_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.drop_zone = BatchDropZone()
        self.drop_zone.setMinimumHeight(72)
        self.drop_zone.paths_dropped.connect(self.paths_selected.emit)
        self.drop_zone.clicked.connect(self._open_files_dialog)
        layout.addWidget(self.drop_zone)

        self.summary = FileSummaryBar()
        self.summary.clear_requested.connect(self.clear_requested.emit)
        self.summary.expand_all.connect(lambda: self.group_list.expand_all())
        self.summary.collapse_all.connect(lambda: self.group_list.collapse_all())
        layout.addWidget(self.summary)

        self.group_list = VideoFileGroupList()
        self.group_list.selection_changed.connect(self._refresh_actions)
        self.group_list.remove_requested.connect(self.remove_file.emit)
        layout.addWidget(self.group_list, 1)

        self.export_options = ExportOptionsWidget()
        self.export_options.options_changed.connect(self._on_options_changed)
        layout.addWidget(self.export_options)

        self.action_bar = ActionBar(batch_mode=True)
        self.action_bar.select_all_toggled.connect(self.group_list.set_all_selected)
        self.action_bar.extract_selected.connect(self.extract_selected.emit)
        self.action_bar.extract_all.connect(self.extract_all.emit)
        self.action_bar.cancel_requested.connect(self.cancel_requested.emit)
        layout.addWidget(self.action_bar)

    def _open_files_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择多个视频文件", "", VIDEO_FILE_FILTER
        )
        if paths:
            self.paths_selected.emit(paths)

    def open_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.paths_selected.emit([folder])

    def begin_files(self, paths: list[str]) -> None:
        for path in paths:
            group = self.group_list.add_group(path)
            group.set_parsing()
        self._update_summary(parsing=f"正在解析 (0/{len(paths)})…")
        self._refresh_actions()

    def on_parsed(self, video: VideoFileInfo) -> None:
        group = self.group_list.get_group(video.file_path)
        if group:
            group.set_success(video)
            opts = self.export_options.get_options()
            group.set_mp3_mode(opts.convert_to_mp3)
        self._update_has_video()
        self._update_summary()
        self._refresh_actions()

    def on_parse_failed(self, file_path: str, message: str) -> None:
        group = self.group_list.get_group(file_path)
        if group:
            group.set_failed(message)
        self._update_summary()
        self._refresh_actions()

    def set_parse_progress(self, done: int, total: int) -> None:
        self._update_summary(parsing=f"正在解析 ({done}/{total})…")

    def remove_path(self, file_path: str) -> None:
        self.group_list.remove_group(file_path)
        self._update_has_video()
        self._update_summary()
        self._refresh_actions()

    def clear(self) -> None:
        self.group_list.clear()
        self.summary.update_summary(0, 0)
        self.export_options.set_has_video(True)
        self.action_bar.set_idle_state()

    def existing_paths(self) -> set[str]:
        return {g.file_path for g in self.group_list.groups()}

    def successful_videos(self) -> list[VideoFileInfo]:
        result = []
        for group in self.group_list.groups():
            if group.video:
                result.append(group.video)
        return result

    def selected_by_file(self) -> dict[str, list]:
        mapping = {}
        for group in self.group_list.groups():
            if group.video:
                mapping[group.file_path] = group.selected_tracks()
        return mapping

    def all_tracks_by_file(self) -> dict[str, list]:
        mapping = {}
        for group in self.group_list.groups():
            if group.video:
                mapping[group.file_path] = list(group.video.audio_tracks)
        return mapping

    def get_export_options(self) -> ExportOptions:
        return self.export_options.get_options()

    def set_mp3_available(self, available: bool) -> None:
        self.export_options.set_mp3_available(available)

    def set_default_output_dir(self, path: str) -> None:
        if path and not self.export_options.output_directory():
            self.export_options.set_output_directory(path)

    def set_extracting(self, extracting: bool) -> None:
        self.action_bar.set_extracting(extracting)
        self.drop_zone.setEnabled(not extracting)
        self.export_options.setEnabled(not extracting)

    def set_progress(self, value: float) -> None:
        self.action_bar.set_progress(value)

    def mark_group_extracting(self, file_path: str, done: int, total: int) -> None:
        group = self.group_list.get_group(file_path)
        if group:
            group.set_extracting(done, total)

    def mark_group_done(self, file_path: str, success: bool) -> None:
        group = self.group_list.get_group(file_path)
        if group:
            group.set_done(success)

    def _update_summary(self, parsing: str = "") -> None:
        files = len(self.group_list.groups())
        tracks = self.group_list.total_tracks()
        self.summary.update_summary(files, tracks, parsing)

    def _update_has_video(self) -> None:
        self.export_options.set_has_video(self.group_list.has_any_video_track())

    def _on_options_changed(self) -> None:
        opts = self.export_options.get_options()
        self.group_list.set_mp3_mode(opts.convert_to_mp3)
        self._refresh_actions()
        self.options_changed.emit()

    def _refresh_actions(self) -> None:
        tracks = self.group_list.total_tracks()
        has_selection = self.group_list.has_any_selection()
        opts = self.export_options.get_options()
        self.action_bar.set_ready_state(
            has_tracks=tracks > 0,
            has_selection=has_selection,
            has_output_dir=bool(opts.output_directory),
            export_video_only=opts.export_video_only,
        )
