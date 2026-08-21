"""可缩放预览、点击与拖入图片。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QLabel

from app.utils.constants import IMAGE_EXTENSIONS


def bgr_to_pixmap(image: np.ndarray) -> QPixmap:
    rgb = image
    if image.ndim == 2:
        qimg = QImage(
            image.data,
            image.shape[1],
            image.shape[0],
            image.strides[0],
            QImage.Format.Format_Grayscale8,
        )
        return QPixmap.fromImage(qimg.copy())
    rgb = image[:, :, ::-1].copy()
    qimg = QImage(
        rgb.data,
        rgb.shape[1],
        rgb.shape[0],
        rgb.strides[0],
        QImage.Format.Format_RGB888,
    )
    return QPixmap.fromImage(qimg.copy())


class ImagePreview(QLabel):
    clicked = Signal()
    file_dropped = Signal(str)

    def __init__(self, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        self._source: QPixmap | None = None
        self._placeholder = placeholder
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(280, 220)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setAcceptDrops(True)
        self.setText(placeholder)
        self.setWordWrap(True)

    def set_pixmap_source(self, pixmap: QPixmap) -> None:
        self._source = pixmap
        self._refresh()

    def set_bgr(self, image: np.ndarray) -> None:
        self.set_pixmap_source(bgr_to_pixmap(image))

    def clear_image(self) -> None:
        self._source = None
        self.setPixmap(QPixmap())
        self.setText(self._placeholder)

    def has_image(self) -> bool:
        return self._source is not None and not self._source.isNull()

    def _refresh(self) -> None:
        if self._source is None or self._source.isNull():
            self.setPixmap(QPixmap())
            self.setText(self._placeholder)
            return
        self.setText("")
        scaled = self._source.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._source is not None:
            self._refresh()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local and Path(local).suffix.lower() in IMAGE_EXTENSIONS:
                self.file_dropped.emit(str(Path(local).resolve()))
                event.acceptProposedAction()
                return
        event.ignore()
