"""深度图生成控制器。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from app.core.depth_engine import DepthCancelled, DepthEngine, imread_unicode
from app.core.depth_models import DepthModelSpec


class DepthSignals(QObject):
    progress = Signal(int, str)
    finished = Signal(object, object)  # gray, color (numpy)
    failed = Signal(str)


class DepthWorker(QRunnable):
    def __init__(
        self,
        engine: DepthEngine,
        image_path: str,
        spec: DepthModelSpec,
        model_path: str | None,
    ) -> None:
        super().__init__()
        self.engine = engine
        self.image_path = image_path
        self.spec = spec
        self.model_path = model_path
        self.signals = DepthSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.progress.emit(2, "正在读取图片…")
            image = imread_unicode(self.image_path)
            gray, color = self.engine.run(
                image,
                self.spec,
                model_path=self.model_path,
                progress_cb=lambda value, text: self.signals.progress.emit(value, text),
            )
            self.signals.progress.emit(100, "完成")
            self.signals.finished.emit(gray, color)
        except DepthCancelled:
            self.signals.failed.emit("已取消")
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))


class DepthController(QObject):
    progress = Signal(int, str)
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.engine = DepthEngine()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def start(
        self,
        image_path: str,
        spec: DepthModelSpec,
        model_path: str | None = None,
    ) -> None:
        if self._busy:
            return
        self._busy = True
        self.engine.reset_cancel()
        worker = DepthWorker(self.engine, image_path, spec, model_path)
        worker.signals.progress.connect(self.progress.emit)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self.pool.start(worker)

    def cancel(self) -> None:
        self.engine.cancel()

    def unload_model(self) -> None:
        self.engine.unload()

    def set_use_gpu(self, enabled: bool) -> None:
        self.engine.set_use_gpu(enabled)

    def runtime_text(self) -> str:
        from app.core.depth_engine import runtime_status_text

        active = self.engine.last_provider if self.engine.has_session else None
        return runtime_status_text(self.engine.use_gpu, active)

    def shutdown(self) -> None:
        self.engine.cancel()
        self.pool.clear()
        self.pool.waitForDone(5000)

    def _on_finished(self, gray, color) -> None:
        self._busy = False
        self.finished.emit(gray, color)

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.failed.emit(message)
