"""文件信息栏组件."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.models import VideoFileInfo
from app.utils.helpers import format_duration, format_file_size


class FileInfoBar(QWidget):
    clear_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.info_label = QLabel("")
        layout.addWidget(self.info_label, 1)
        self.clear_btn = QPushButton("✕ 清除")
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        layout.addWidget(self.clear_btn)
        self.hide()

    def show_info(self, video: VideoFileInfo) -> None:
        text = (
            f"当前文件: {video.file_name}  |  "
            f"{format_file_size(video.file_size)}  |  "
            f"{format_duration(video.duration)}  |  "
            f"{video.track_count} 条音轨"
        )
        self.info_label.setText(text)
        self.show()

    def clear(self) -> None:
        self.info_label.setText("")
        self.hide()


class FileSummaryBar(QWidget):
    clear_requested = Signal()
    expand_all = Signal()
    collapse_all = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.info_label = QLabel("已加载文件列表:")
        layout.addWidget(self.info_label, 1)
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)
        self.expand_btn = QPushButton("全部展开")
        self.expand_btn.clicked.connect(self.expand_all.emit)
        layout.addWidget(self.expand_btn)
        self.collapse_btn = QPushButton("全部折叠")
        self.collapse_btn.clicked.connect(self.collapse_all.emit)
        layout.addWidget(self.collapse_btn)
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        layout.addWidget(self.clear_btn)

    def update_summary(self, file_count: int, track_count: int, parsing: str = "") -> None:
        self.info_label.setText(
            f"已加载文件列表: (共 {file_count} 个视频, {track_count} 条音轨)"
        )
        self.progress_label.setText(parsing)
