"""导出选项组件."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models import ExportOptions


class ExportOptionsWidget(QWidget):
    options_changed = Signal()
    directory_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("导出目录:"))
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setPlaceholderText("请选择输出目录…")
        dir_row.addWidget(self.dir_edit, 1)
        self.browse_btn = QPushButton("浏览…")
        self.browse_btn.clicked.connect(self._browse)
        dir_row.addWidget(self.browse_btn)
        self.warn_label = QLabel("")
        dir_row.addWidget(self.warn_label)
        layout.addLayout(dir_row)

        layout.addWidget(QLabel("导出格式选项:"))
        self.mp3_check = QCheckBox("转换为 MP3 格式")
        self.mp3_check.setToolTip(
            "勾选后，所有提取的音频将统一转码为 MP3 (libmp3lame)\n"
            "默认比特率 192 kbps，采样率与声道保持原始"
        )
        self.mp3_check.stateChanged.connect(self._emit_changed)
        layout.addWidget(self.mp3_check)

        self.video_only_check = QCheckBox("导出去除音频的纯视频")
        self.video_only_check.setToolTip(
            "使用 -c copy 流复制视频轨，不重新编码\n"
            "输出文件名: {原文件名}_no_audio.{原扩展名}"
        )
        self.video_only_check.stateChanged.connect(self._emit_changed)
        layout.addWidget(self.video_only_check)

        self._has_video = True
        self._mp3_available = True

    def _browse(self) -> None:
        start = self.dir_edit.text() or str(Path.home() / "Music")
        chosen = QFileDialog.getExistingDirectory(self, "选择导出目录", start)
        if chosen:
            self.set_output_directory(chosen)

    def set_output_directory(self, path: str) -> None:
        self.dir_edit.setText(path)
        writable = Path(path).exists() and Path(path).is_dir()
        self.warn_label.setText("" if writable else "路径无效")
        self.directory_changed.emit(path)
        self.options_changed.emit()

    def output_directory(self) -> str:
        return self.dir_edit.text().strip()

    def set_mp3_available(self, available: bool) -> None:
        self._mp3_available = available
        self.mp3_check.setEnabled(available)
        if not available:
            self.mp3_check.setChecked(False)
            self.mp3_check.setToolTip(
                "未检测到 libmp3lame 编码器，MP3 转换功能不可用。"
                "请安装包含 libmp3lame 的 FFmpeg 版本。"
            )

    def set_has_video(self, has_video: bool) -> None:
        self._has_video = has_video
        self.video_only_check.setVisible(has_video)
        if not has_video:
            self.video_only_check.setChecked(False)

    def get_options(self) -> ExportOptions:
        return ExportOptions(
            convert_to_mp3=self.mp3_check.isChecked(),
            export_video_only=self.video_only_check.isChecked() and self._has_video,
            output_directory=self.output_directory() or None,
        )

    def _emit_changed(self) -> None:
        self.options_changed.emit()
