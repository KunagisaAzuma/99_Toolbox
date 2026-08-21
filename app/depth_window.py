"""深度图生成工具窗口。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, Qt, QStandardPaths
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QStatusBar, QVBoxLayout, QWidget

from app.core.depth_engine import imread_unicode, imwrite_unicode
from app.core.depth_models import spec_by_id
from app.core.model_downloader import delete_model, is_model_ready
from app.depth_controller import DepthController
from app.ui.depth_page import EXPORT_GRAY, DepthPage
from app.ui.model_choice_dialog import (
    download_selected_models,
    pick_models_to_delete,
    pick_models_to_download,
)
from app.utils.constants import (
    APP_AUTHOR_LINE,
    APP_ORG,
    DEPTH_TOOL_NAME,
    IMAGE_EXTENSIONS,
)

DEFAULT_DEPTH_MODEL_ID = "da_v2_s"


class DepthToolWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(DEPTH_TOOL_NAME)
        self.setWindowIcon(QIcon())
        self.resize(960, 640)

        self.settings = QSettings(APP_ORG, DEPTH_TOOL_NAME)
        self.controller = DepthController(self)
        self._image_path: str | None = None
        self._result_color: np.ndarray | None = None
        self._result_gray: np.ndarray | None = None

        self.page = DepthPage()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.page, 1)
        self.author_label = QLabel(APP_AUTHOR_LINE)
        self.author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.author_label)
        self.setCentralWidget(central)
        self.menuBar().hide()

        bar = QStatusBar()
        self.setStatusBar(bar)
        self.status_label = QLabel("就绪")
        bar.addWidget(self.status_label, 1)
        self.runtime_label = QLabel("")
        bar.addPermanentWidget(self.runtime_label)

        self._connect()
        self._restore()
        self._refresh_runtime()
        self.page.set_busy(False)
        self.page.generate_btn.setEnabled(False)

    def _connect(self) -> None:
        self.page.import_requested.connect(self._import_image)
        self.page.file_dropped.connect(self._load_image)
        self.page.generate_requested.connect(self._generate)
        self.page.export_requested.connect(self._export)
        self.page.cancel_requested.connect(self._cancel)
        self.page.download_model_requested.connect(self._download_models)
        self.page.delete_model_requested.connect(self._delete_models)
        self.page.export_combo.currentIndexChanged.connect(self._refresh_preview)
        self.controller.progress.connect(self._on_progress)
        self.controller.finished.connect(self._on_finished)
        self.controller.failed.connect(self._on_failed)

    def _restore(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.page.refresh_models()
        model_id = self.settings.value("model_id", DEFAULT_DEPTH_MODEL_ID, type=str)
        if model_id:
            index = self.page.model_combo.findData(model_id)
            if index >= 0:
                self.page.model_combo.setCurrentIndex(index)
        export_mode = self.settings.value("export_mode", "", type=str)
        if export_mode:
            index = self.page.export_combo.findData(export_mode)
            if index >= 0:
                self.page.export_combo.setCurrentIndex(index)

    def closeEvent(self, event) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("model_id", self.page.current_model_id())
        self.settings.setValue("export_mode", self.page.export_mode())
        self.controller.shutdown()
        super().closeEvent(event)

    def _refresh_runtime(self) -> None:
        self.runtime_label.setText(self.controller.runtime_text())

    def _pictures_dir(self) -> str:
        saved = self.settings.value("last_image_dir", "", type=str)
        if saved and Path(saved).is_dir():
            return saved
        return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)

    def _import_image(self) -> None:
        path = self.page.choose_image(self._pictures_dir())
        if path:
            self._load_image(path)

    def _load_image(self, path: str) -> None:
        if Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
            QMessageBox.warning(self, "提示", "请选择图片文件")
            return
        try:
            image = imread_unicode(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self._image_path = path
        self._result_color = None
        self._result_gray = None
        self.page.source_view.set_bgr(image)
        self.page.result_view.clear_image()
        self.page.export_btn.setEnabled(False)
        self.page.generate_btn.setEnabled(True)
        self.settings.setValue("last_image_dir", str(Path(path).parent))
        self.status_label.setText(f"已导入: {Path(path).name}")
        self.page.reset_progress()

    def _current_spec(self):
        spec = spec_by_id(self.page.current_model_id())
        if spec is None:
            raise FileNotFoundError("未知模型")
        return spec

    def _download_models(self) -> None:
        selected = pick_models_to_download(self)
        if not selected:
            return
        if download_selected_models(selected, self):
            self.page.refresh_models()
            self.status_label.setText("模型下载完成")
        else:
            self.status_label.setText("模型下载已取消或失败")

    def _delete_models(self) -> None:
        selected = pick_models_to_delete(self)
        if not selected:
            return
        for spec in selected:
            delete_model(spec)
        self.controller.unload_model()
        self.page.refresh_models()
        names = "、".join(spec.short_name for spec in selected)
        self.status_label.setText(f"已删除: {names}")

    def _generate(self) -> None:
        if not self._image_path:
            QMessageBox.information(self, "提示", "请先导入图片")
            return
        try:
            spec = self._current_spec()
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "提示", str(exc))
            return
        if not is_model_ready(spec):
            reply = QMessageBox.question(
                self,
                "下载模型",
                f"「{spec.title}」尚未下载或不完整，是否现在下载？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            if not download_selected_models([spec], self):
                self.status_label.setText("未下载模型，已取消生成")
                return
            self.page.refresh_models()
        self.page.set_busy(True)
        self.page.set_progress(1)
        self.status_label.setText("正在准备…")
        self.controller.start(self._image_path, spec, None)

    def _cancel(self) -> None:
        self.controller.cancel()
        self.status_label.setText("正在取消…")

    def _on_progress(self, value: int, text: str) -> None:
        if 55 <= value < 90:
            self.page.set_busy_undetermined()
        else:
            self.page.set_progress(value)
        self.status_label.setText(text)

    def _on_finished(self, gray, color) -> None:
        self._result_gray = gray
        self._result_color = color
        self._refresh_preview()
        self.page.set_busy(False)
        self.page.set_progress(100)
        self.page.export_btn.setEnabled(True)
        self._refresh_runtime()
        self.status_label.setText("生成完成")

    def _refresh_preview(self) -> None:
        if self._result_color is None or self._result_gray is None:
            return
        if self.page.export_mode() == EXPORT_GRAY:
            self.page.result_view.set_bgr(self._result_gray)
        else:
            self.page.result_view.set_bgr(self._result_color)

    def _on_failed(self, message: str) -> None:
        self.page.set_busy(False)
        self.page.reset_progress()
        self._refresh_runtime()
        if message == "已取消":
            self.status_label.setText("已取消")
            return
        self.status_label.setText("生成失败")
        QMessageBox.warning(self, "生成失败", message)

    def _export_image(self) -> np.ndarray | None:
        if self.page.export_mode() == EXPORT_GRAY:
            return self._result_gray
        return self._result_color

    def _export(self) -> None:
        image = self._export_image()
        if image is None:
            return
        stem = Path(self._image_path).stem if self._image_path else "depth"
        suffix = "_depth_gray" if self.page.export_mode() == EXPORT_GRAY else "_depth"
        suggested = str(Path(self._pictures_dir()) / f"{stem}{suffix}.png")
        path = self.page.choose_export(suggested)
        if not path:
            return
        try:
            imwrite_unicode(path, image)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.settings.setValue("last_image_dir", str(Path(path).parent))
        self.status_label.setText(f"已导出: {Path(path).name}")
