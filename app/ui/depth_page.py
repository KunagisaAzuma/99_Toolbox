"""深度图生成页面。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.depth_models import DEPTH_MODELS
from app.core.model_downloader import combo_label
from app.ui.image_preview import ImagePreview
from app.utils.constants import IMAGE_FILE_FILTER

EXPORT_COLOR = "color"
EXPORT_GRAY = "gray"


class DepthPage(QWidget):
    import_requested = Signal()
    generate_requested = Signal()
    export_requested = Signal()
    cancel_requested = Signal()
    download_model_requested = Signal()
    delete_model_requested = Signal()
    file_dropped = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        self.import_btn = QPushButton("导入图片")
        self.import_btn.clicked.connect(self.import_requested.emit)
        row.addWidget(self.import_btn)

        row.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.refresh_models()
        row.addWidget(self.model_combo, 1)

        self.download_btn = QPushButton("下载模型")
        self.download_btn.clicked.connect(self.download_model_requested.emit)
        row.addWidget(self.download_btn)

        self.delete_btn = QPushButton("删除模型")
        self.delete_btn.clicked.connect(self.delete_model_requested.emit)
        row.addWidget(self.delete_btn)
        layout.addLayout(row)

        action_row = QHBoxLayout()
        self.generate_btn = QPushButton("生成深度图")
        self.generate_btn.clicked.connect(self.generate_requested.emit)
        action_row.addWidget(self.generate_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        self.cancel_btn.setVisible(False)
        action_row.addWidget(self.cancel_btn)

        action_row.addWidget(QLabel("导出样式:"))
        self.export_combo = QComboBox()
        self.export_combo.addItem("彩色（正常）", EXPORT_COLOR)
        self.export_combo.addItem("黑白", EXPORT_GRAY)
        action_row.addWidget(self.export_combo)
        self.export_btn = QPushButton("导出")
        self.export_btn.clicked.connect(self.export_requested.emit)
        self.export_btn.setEnabled(False)
        action_row.addWidget(self.export_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        splitter = QSplitter()
        self.source_view = ImagePreview("点击导入或拖入图片")
        self.result_view = ImagePreview("生成后的深度图显示在这里")
        self.source_view.clicked.connect(self.import_requested.emit)
        self.source_view.file_dropped.connect(self.file_dropped.emit)
        splitter.addWidget(self.source_view)
        splitter.addWidget(self.result_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

    def refresh_models(self) -> None:
        current = self.current_model_id() if self.model_combo.count() else ""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for spec in DEPTH_MODELS:
            self.model_combo.addItem(combo_label(spec), spec.model_id)
        if current:
            index = self.model_combo.findData(current)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)

    def current_model_id(self) -> str:
        return str(self.model_combo.currentData() or "")

    def export_mode(self) -> str:
        return str(self.export_combo.currentData() or EXPORT_COLOR)

    def set_busy(self, busy: bool) -> None:
        self.import_btn.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.download_btn.setEnabled(not busy)
        self.delete_btn.setEnabled(not busy)
        self.export_combo.setEnabled(not busy)
        self.generate_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy and self.result_view.has_image())
        self.cancel_btn.setVisible(busy)
        if not busy:
            self.generate_btn.setEnabled(self.source_view.has_image())

    def set_progress(self, value: int) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(max(0, min(100, value)))

    def set_busy_undetermined(self) -> None:
        self.progress.setRange(0, 0)

    def reset_progress(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

    def choose_image(self, start_dir: str = "") -> str:
        path, _ = QFileDialog.getOpenFileName(self, "导入图片", start_dir, IMAGE_FILE_FILTER)
        return path

    def choose_export(self, suggested: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出深度图",
            suggested,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*.*)",
        )
        return path
