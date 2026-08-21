"""ONNX 深度估计：下载模型、预处理、推理、着色。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from app.core.depth_models import DepthModelSpec
from app.core.model_downloader import (
    DownloadCancelled,
    download_with_mirrors,
    is_model_ready,
    local_model_path,
    purge_incomplete_download,
)


class DepthCancelled(Exception):
    """用户取消下载或推理。"""


ProgressCb = Callable[[int, str], None]


def imread_unicode(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("无法读取图片，请确认文件格式受支持")
    return image


def imwrite_unicode(path: str, image: np.ndarray) -> None:
    suffix = Path(path).suffix.lower() or ".png"
    ok, buf = cv2.imencode(suffix, image)
    if not ok:
        raise ValueError("无法编码导出图片")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(path)


def runtime_status_text(use_gpu: bool = True, active: str | None = None) -> str:
    gpu = gpu_providers()
    if active:
        name = _provider_display(active)
        return f"推理: {name}"
    if use_gpu and gpu:
        return f"ONNX Runtime（GPU 可用: {_provider_display(gpu[0])}）"
    if use_gpu and not gpu:
        return "ONNX Runtime（未检测到 GPU，将用 CPU）"
    return "ONNX Runtime（CPU）"


def gpu_providers() -> list[str]:
    available = set(ort.get_available_providers())
    order = (
        "CUDAExecutionProvider",
        "TensorrtExecutionProvider",
        "DmlExecutionProvider",
        "ROCMExecutionProvider",
        "CoreMLExecutionProvider",
    )
    return [name for name in order if name in available]


def gpu_available() -> bool:
    return bool(gpu_providers())


def _provider_display(name: str) -> str:
    mapping = {
        "CUDAExecutionProvider": "CUDA GPU",
        "TensorrtExecutionProvider": "TensorRT GPU",
        "DmlExecutionProvider": "DirectML GPU",
        "ROCMExecutionProvider": "ROCm GPU",
        "CoreMLExecutionProvider": "CoreML",
        "CPUExecutionProvider": "CPU",
    }
    return mapping.get(name, name)


def session_providers(use_gpu: bool) -> list[str]:
    cpu = ["CPUExecutionProvider"]
    if not use_gpu:
        return cpu
    gpu = gpu_providers()
    return gpu + cpu if gpu else cpu


def ensure_model(
    spec: DepthModelSpec,
    progress_cb: ProgressCb | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    path = local_model_path(spec)
    if is_model_ready(spec):
        return path
    if not spec.url:
        raise FileNotFoundError("未提供模型下载地址")
    if progress_cb:
        progress_cb(5, f"正在下载模型（{spec.size_label}）…")

    def _on_progress(percent: float, text: str, _threads=None) -> None:
        if progress_cb:
            progress_cb(5 + int(min(percent, 100.0) * 0.3), text or f"正在下载… {percent:.0f}%")

    try:
        download_with_mirrors(
            spec.url,
            path,
            spec.expected_bytes,
            cancelled or (lambda: False),
            on_progress=_on_progress,
        )
    except DownloadCancelled as exc:
        raise DepthCancelled(str(exc)) from exc
    if not is_model_ready(spec):
        raise FileNotFoundError("模型下载后校验失败，请重新下载")
    return path


def _as_hw(depth: np.ndarray) -> np.ndarray:
    array = np.asarray(depth)
    while array.ndim > 2:
        array = array[0]
    return array.astype(np.float32)


def _preprocess_midas(bgr: np.ndarray, size: int, nchw: bool) -> np.ndarray:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    resized = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_CUBIC)
    if nchw:
        return np.transpose(resized, (2, 0, 1))[None].astype(np.float32)
    return resized[None].astype(np.float32)


def _preprocess_midas_dpt(bgr: np.ndarray, size: int, nchw: bool) -> np.ndarray:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    resized = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_CUBIC)
    resized = (resized - 0.5) / 0.5
    if nchw:
        return np.transpose(resized, (2, 0, 1))[None].astype(np.float32)
    return resized[None].astype(np.float32)


def _preprocess_depth_anything(bgr: np.ndarray, size: int, nchw: bool) -> np.ndarray:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    resized = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_CUBIC)
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    resized = (resized - mean) / std
    if nchw:
        return np.transpose(resized, (2, 0, 1))[None].astype(np.float32)
    return resized[None].astype(np.float32)


def _infer_layout(input_shape: list) -> tuple[bool, int | None]:
    dims = []
    for item in input_shape:
        dims.append(item if isinstance(item, int) else 0)
    nchw = True
    size = None
    if len(dims) == 4:
        if dims[1] == 3:
            nchw = True
            size = dims[2] if dims[2] > 0 else dims[3]
        elif dims[3] == 3:
            nchw = False
            size = dims[1] if dims[1] > 0 else dims[2]
    return nchw, size if size and size > 0 else None


def colorize_depth(depth_hw: np.ndarray, orig_wh: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    depth = depth_hw.astype(np.float32)
    vmin, vmax = float(depth.min()), float(depth.max())
    if vmax - vmin < 1e-6:
        norm = np.zeros_like(depth, dtype=np.uint8)
    else:
        norm = ((depth - vmin) / (vmax - vmin) * 255.0).astype(np.uint8)
    orig_w, orig_h = orig_wh
    gray = cv2.resize(norm, (orig_w, orig_h), interpolation=cv2.INTER_CUBIC)
    color = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
    return gray, color


class DepthEngine:
    def __init__(self) -> None:
        self._session: ort.InferenceSession | None = None
        self._loaded_key: str | None = None
        self._cancelled = False
        self.use_gpu = True
        self.last_provider = "CPUExecutionProvider"

    def set_use_gpu(self, enabled: bool) -> None:
        if self.use_gpu != enabled:
            self.use_gpu = enabled
            self.unload()

    def cancel(self) -> None:
        self._cancelled = True

    def reset_cancel(self) -> None:
        self._cancelled = False

    def _is_cancelled(self) -> bool:
        return self._cancelled

    def load_session(
        self,
        model_path: str,
        cache_key: str,
        progress_cb: ProgressCb | None = None,
    ) -> ort.InferenceSession:
        key = f"{cache_key}|gpu={self.use_gpu}"
        if self._session is not None and self._loaded_key == key:
            return self._session
        if progress_cb:
            progress_cb(40, "正在加载 ONNX 模型…")
        providers = session_providers(self.use_gpu)
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        try:
            session = ort.InferenceSession(model_path, sess_options=options, providers=providers)
        except Exception as exc:
            message = str(exc)
            if "INVALID_PROTOBUF" in message or "Protobuf parsing failed" in message:
                purge_incomplete_download(Path(model_path))
                raise RuntimeError(
                    "模型文件已损坏或不完整，已自动删除。请重新下载该模型后再生成。"
                ) from exc
            raise
        self._session = session
        self._loaded_key = key
        used = session.get_providers()
        self.last_provider = used[0] if used else "CPUExecutionProvider"
        return session

    def unload(self) -> None:
        self._session = None
        self._loaded_key = None

    @property
    def has_session(self) -> bool:
        return self._session is not None

    def run(
        self,
        image_bgr: np.ndarray,
        spec: DepthModelSpec,
        model_path: str | None = None,
        progress_cb: ProgressCb | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        self.reset_cancel()
        if model_path is None:
            model_path = str(ensure_model(spec, progress_cb, self._is_cancelled))
        if self._is_cancelled():
            raise DepthCancelled("已取消")
        session = self.load_session(model_path, spec.model_id + ":" + model_path, progress_cb)
        if progress_cb:
            progress_cb(50, "正在预处理图片…")
        inp = session.get_inputs()[0]
        nchw, inferred_size = _infer_layout(list(inp.shape))
        size = inferred_size or spec.input_size
        family = spec.family
        if family == "midas":
            tensor = _preprocess_midas(image_bgr, size, nchw)
        elif family == "midas_dpt":
            tensor = _preprocess_midas_dpt(image_bgr, size, nchw)
        else:
            tensor = _preprocess_depth_anything(image_bgr, size, nchw)
        if self._is_cancelled():
            raise DepthCancelled("已取消")
        if progress_cb:
            progress_cb(60, "正在生成深度图…")
        raw = session.run(None, {inp.name: tensor})[0]
        if progress_cb:
            progress_cb(90, "正在着色…")
        depth_hw = _as_hw(raw)
        orig_h, orig_w = image_bgr.shape[:2]
        return colorize_depth(depth_hw, (orig_w, orig_h))
