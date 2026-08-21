"""拖拽区域组件."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from app.utils.constants import VIDEO_EXTENSIONS


class DropZone(QFrame):
    """单视频拖拽区域：接受单个视频或文件夹（取第一个视频）."""

    file_dropped = Signal(str)
    folder_hint = Signal(str)  # 拖入文件夹时提示

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel("将视频文件拖拽到此处\n或点击选择文件")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)
        self._set_idle_style()

    def _set_idle_style(self) -> None:
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self._label.setText("将视频文件拖拽到此处\n或点击选择文件")

    def _set_hover_style(self) -> None:
        self.setFrameShadow(QFrame.Shadow.Raised)
        self._label.setText("释放以导入")

    clicked = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover_style()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_idle_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_idle_style()
        urls = event.mimeData().urls()
        if not urls:
            return
        local = urls[0].toLocalFile()
        if not local:
            return
        path = Path(local)
        if path.is_dir():
            videos = [
                p
                for p in sorted(path.iterdir())
                if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
            ]
            if videos:
                self.folder_hint.emit(
                    "检测到文件夹，已导入第一个视频。批量处理请使用「批量处理」页面。"
                )
                self.file_dropped.emit(str(videos[0].resolve()))
            return
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            self.file_dropped.emit(str(path.resolve()))
            event.acceptProposedAction()


class BatchDropZone(QFrame):
    """批量拖拽区域：接受多文件、文件夹或混合."""

    paths_dropped = Signal(list)
    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(72)
        self.setMaximumHeight(96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel(
            "将多个视频文件或文件夹拖拽到此处\n支持同时拖入文件和文件夹混合导入\n或点击选择"
        )
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)
        self._set_idle_style()

    def _set_idle_style(self) -> None:
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self._label.setText(
            "将多个视频文件或文件夹拖拽到此处\n支持同时拖入文件和文件夹混合导入\n或点击选择"
        )

    def _set_hover_style(self) -> None:
        self.setFrameShadow(QFrame.Shadow.Raised)
        self._label.setText("释放以导入")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover_style()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_idle_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_idle_style()
        paths: list[str] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                paths.append(local)
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()
