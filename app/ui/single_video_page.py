"""单视频处理页面."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout, QWidget

from app.models import AudioTrackInfo, ExportOptions, VideoFileInfo
from app.utils.constants import VIDEO_FILE_FILTER

from .action_bar import ActionBar
from .drop_zone import DropZone
from .export_options_widget import ExportOptionsWidget
from .file_info_bar import FileInfoBar
from .track_list import TrackListWidget


class SingleVideoPage(QWidget):
    file_selected = Signal(str)
    clear_requested = Signal()
    extract_selected = Signal()
    extract_all = Signal()
    cancel_requested = Signal()
    options_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.video: VideoFileInfo | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self.file_selected.emit)
        self.drop_zone.clicked.connect(self._open_file_dialog)
        self.drop_zone.folder_hint.connect(self._show_hint)
        layout.addWidget(self.drop_zone)

        self.file_info = FileInfoBar()
        self.file_info.clear_requested.connect(self.clear_requested.emit)
        layout.addWidget(self.file_info)

        self.track_list = TrackListWidget()
        self.track_list.selection_changed.connect(self._refresh_actions)
        layout.addWidget(self.track_list, 1)

        self.export_options = ExportOptionsWidget()
        self.export_options.options_changed.connect(self._on_options_changed)
        layout.addWidget(self.export_options)

        self.action_bar = ActionBar(batch_mode=False)
        self.action_bar.select_all_toggled.connect(self.track_list.set_all_selected)
        self.action_bar.extract_selected.connect(self.extract_selected.emit)
        self.action_bar.extract_all.connect(self.extract_all.emit)
        self.action_bar.cancel_requested.connect(self.cancel_requested.emit)
        layout.addWidget(self.action_bar)

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开视频文件", "", VIDEO_FILE_FILTER)
        if path:
            self.file_selected.emit(path)

    def _show_hint(self, message: str) -> None:
        QMessageBox.information(self, "提示", message)

    def show_video(self, video: VideoFileInfo) -> None:
        self.video = video
        self.file_info.show_info(video)
        self.track_list.render_tracks(video.audio_tracks)
        self.export_options.set_has_video(video.has_video)
        self._refresh_actions()

    def clear(self) -> None:
        self.video = None
        self.file_info.clear()
        self.track_list.clear()
        self.export_options.set_has_video(True)
        self.action_bar.set_idle_state()

    def selected_tracks(self) -> list[AudioTrackInfo]:
        return self.track_list.selected_tracks()

    def all_tracks(self) -> list[AudioTrackInfo]:
        return self.track_list.all_tracks()

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

    def _on_options_changed(self) -> None:
        opts = self.export_options.get_options()
        self.track_list.set_mp3_mode(opts.convert_to_mp3)
        self._refresh_actions()
        self.options_changed.emit()

    def _refresh_actions(self) -> None:
        tracks = self.track_list.all_tracks()
        selected = self.track_list.selected_tracks()
        opts = self.export_options.get_options()
        self.action_bar.set_select_all_checked(
            bool(tracks) and len(selected) == len(tracks)
        )
        self.action_bar.set_ready_state(
            has_tracks=bool(tracks),
            has_selection=bool(selected),
            has_output_dir=bool(opts.output_directory),
            export_video_only=opts.export_video_only,
        )
