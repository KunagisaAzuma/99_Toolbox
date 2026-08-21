"""工具箱首页：仅系统原生控件，无 QSS。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.tools import ToolSpec, all_tools
from app.utils.constants import APP_NAME


class ToolboxWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon())
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.MSWindowsFixedSizeDialogHint
        )
        self.setFixedSize(250, 420)

        self._open_windows: list[QWidget] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for spec in all_tools():
            button = QPushButton(spec.title)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, s=spec: self._open_tool(s))
            layout.addWidget(button)

        layout.addStretch(1)

        exit_btn = QPushButton("退出")
        exit_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        exit_btn.clicked.connect(self._quit)
        layout.addWidget(exit_btn)

    def _open_tool(self, spec: ToolSpec) -> None:
        window = spec.factory()
        if window is None:
            return
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        offset = 28 * (len(self._open_windows) % 8)
        window.move(self.x() + 40 + offset, self.y() + 40 + offset)
        window.destroyed.connect(lambda _obj=None, w=window: self._forget(w))
        self._open_windows.append(window)
        window.show()
        window.raise_()
        window.activateWindow()

    def _forget(self, window: QWidget) -> None:
        if window in self._open_windows:
            self._open_windows.remove(window)

    def _quit(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
