"""打开深度图工具前的模型下载对话框（系统原生，无 QSS）。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.aria2_runner import CONNECTIONS, ThreadProgress
from app.core.depth_models import DepthModelSpec
from app.core.model_downloader import (
    DownloadCancelled,
    download_models,
    format_bytes,
    is_model_ready,
    missing_models,
)
from app.utils.constants import DEPTH_TOOL_NAME


def _speed_text(bps: int) -> str:
    if bps <= 0:
        return "0 B/s"
    value = float(bps)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024.0 or unit == "GB/s":
            if unit == "B/s":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{bps} B/s"


class _DownloadWorker(QObject):
    progress = Signal(int, str)
    threads = Signal(object)
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, specs: list[DepthModelSpec]) -> None:
        super().__init__()
        self._specs = specs
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            download_models(
                self._specs,
                progress_cb=lambda value, text: self.progress.emit(value, text),
                cancelled=lambda: self._cancel,
                thread_cb=lambda items: self.threads.emit(items),
            )
            if self._cancel:
                self.failed.emit("已取消")
                return
            self.succeeded.emit()
        except DownloadCancelled:
            self.failed.emit("已取消")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ModelDownloadDialog(QDialog):
    def __init__(self, specs: list[DepthModelSpec], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"下载模型 · {DEPTH_TOOL_NAME}")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.resize(520, 520)
        self._ok = False

        layout = QVBoxLayout(self)
        self.hint = QLabel("正在下载模型…")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        layout.addWidget(QLabel("总体进度"))
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        layout.addWidget(QLabel("各线程进度"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        self._thread_bars: list[QProgressBar] = []
        self._thread_speeds: list[QLabel] = []
        for index in range(CONNECTIONS):
            name = QLabel(f"线程 {index + 1:02d}")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            speed = QLabel("0 B/s")
            speed.setMinimumWidth(72)
            speed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(name, index, 0)
            grid.addWidget(bar, index, 1)
            grid.addWidget(speed, index, 2)
            self._thread_bars.append(bar)
            self._thread_speeds.append(speed)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self._thread = QThread(self)
        self._worker = _DownloadWorker(specs)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.threads.connect(self._on_threads)
        self._worker.succeeded.connect(self._on_ok)
        self._worker.failed.connect(self._on_fail)
        self._thread.start()

    def _on_progress(self, value: int, text: str) -> None:
        self.bar.setRange(0, 100)
        self.bar.setValue(max(0, min(100, value)))
        self.hint.setText(text)

    def _on_threads(self, items: object) -> None:
        threads: list[ThreadProgress] = list(items) if isinstance(items, list) else []
        by_index = {item.index: item for item in threads if isinstance(item, ThreadProgress)}
        for index, bar in enumerate(self._thread_bars, start=1):
            item = by_index.get(index)
            if item is None:
                bar.setValue(0)
                self._thread_speeds[index - 1].setText("0 B/s")
                continue
            bar.setValue(int(max(0, min(100, item.percent))))
            self._thread_speeds[index - 1].setText(_speed_text(item.speed_bps))

    def _on_cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.hint.setText("正在取消…")
        self._worker.cancel()

    def _cleanup_thread(self) -> None:
        self._thread.quit()
        self._thread.wait(8000)

    def _on_ok(self) -> None:
        self._ok = True
        self.bar.setValue(100)
        for bar in self._thread_bars:
            bar.setValue(100)
        for label in self._thread_speeds:
            label.setText("0 B/s")
        self._cleanup_thread()
        self.accept()

    def _on_fail(self, message: str) -> None:
        self._cleanup_thread()
        if message != "已取消":
            QMessageBox.warning(self, "下载失败", message)
        self.reject()

    def closeEvent(self, event) -> None:
        if self._thread.isRunning():
            self._worker.cancel()
            self._cleanup_thread()
        super().closeEvent(event)


def ensure_depth_models(
    parent: QWidget | None = None,
    specs: list[DepthModelSpec] | None = None,
) -> bool:
    first_open = specs is None
    if first_open:
        pending = missing_models()
        prompt = "使用深度图生成需要下载模型文件。不下载将退出该工具。"
        reject_text = "退出"
    else:
        pending = [spec for spec in specs if spec.url and not is_model_ready(spec)]
        prompt = "当前模型文件已删除，需要重新下载后才能生成。"
        reject_text = "取消"
    if not pending:
        return True
    parent = parent or QApplication.activeWindow()
    total = sum(spec.expected_bytes for spec in pending)
    lines = "\n".join(f"· {spec.title}（{spec.size_label}）" for spec in pending)
    box = QMessageBox(parent)
    box.setWindowTitle(DEPTH_TOOL_NAME)
    box.setText(prompt)
    box.setInformativeText(f"{lines}\n\n合计约 {format_bytes(total)}")
    download_btn = box.addButton("下载", QMessageBox.ButtonRole.AcceptRole)
    box.addButton(reject_text, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(download_btn)
    box.exec()
    if box.clickedButton() != download_btn:
        return False
    dialog = ModelDownloadDialog(pending, parent)
    return dialog.exec() == QDialog.DialogCode.Accepted
