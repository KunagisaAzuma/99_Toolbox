"""深度估计 ONNX 模型预设。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DepthModelSpec:
    model_id: str
    short_name: str
    speed_tag: str  # 速度快 | 精度高
    family: str  # midas | midas_dpt | depth_anything_v2
    filename: str
    url: str | None
    input_size: int
    size_label: str
    expected_bytes: int = 0

    @property
    def title(self) -> str:
        return f"{self.speed_tag} · {self.short_name}"


DEPTH_MODELS: tuple[DepthModelSpec, ...] = (
    DepthModelSpec(
        model_id="midas_small",
        short_name="MiDaS v2.1 Small",
        speed_tag="速度快",
        family="midas",
        filename="midas_v21_small.onnx",
        url="https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx",
        input_size=256,
        size_label="约 64 MB",
        expected_bytes=66_845_081,
    ),
    DepthModelSpec(
        model_id="midas_large",
        short_name="MiDaS v2.1 Large",
        speed_tag="精度高",
        family="midas",
        filename="midas_v21_large.onnx",
        url="https://github.com/isl-org/MiDaS/releases/download/v2_1/model-f6b98070.onnx",
        input_size=384,
        size_label="约 397 MB",
        expected_bytes=416_390_349,
    ),
    DepthModelSpec(
        model_id="midas_dpt_hybrid",
        short_name="MiDaS v3 DPT Hybrid",
        speed_tag="精度高",
        family="midas_dpt",
        filename="midas_dpt_hybrid_384.onnx",
        url="https://github.com/parkchamchi/MiDaS/releases/download/22.12.07/dpt_hybrid_384.onnx",
        input_size=384,
        size_label="约 508 MB",
        expected_bytes=532_893_696,
    ),
    DepthModelSpec(
        model_id="midas_dpt_large",
        short_name="MiDaS v3 DPT Large",
        speed_tag="精度高",
        family="midas_dpt",
        filename="midas_dpt_large_384.onnx",
        url="https://github.com/parkchamchi/MiDaS/releases/download/22.12.07/dpt_large_384.onnx",
        input_size=384,
        size_label="约 1.3 GB",
        expected_bytes=1_367_703_552,
    ),
    DepthModelSpec(
        model_id="da_v2_s",
        short_name="Depth Anything V2 Small",
        speed_tag="速度快",
        family="depth_anything_v2",
        filename="depth_anything_v2_vits.onnx",
        url=(
            "https://github.com/fabio-sim/Depth-Anything-ONNX/releases/"
            "download/v2.0.0/depth_anything_v2_vits.onnx"
        ),
        input_size=518,
        size_label="约 95 MB",
        expected_bytes=99_418_112,
    ),
    DepthModelSpec(
        model_id="da_v2_b",
        short_name="Depth Anything V2 Base",
        speed_tag="精度高",
        family="depth_anything_v2",
        filename="depth_anything_v2_vitb.onnx",
        url=(
            "https://github.com/fabio-sim/Depth-Anything-ONNX/releases/"
            "download/v2.0.0/depth_anything_v2_vitb.onnx"
        ),
        input_size=518,
        size_label="约 371 MB",
        expected_bytes=389_231_411,
    ),
    DepthModelSpec(
        model_id="da_v2_l",
        short_name="Depth Anything V2 Large",
        speed_tag="精度高",
        family="depth_anything_v2",
        filename="depth_anything_v2_vitl.onnx",
        url=(
            "https://github.com/fabio-sim/Depth-Anything-ONNX/releases/"
            "download/v2.0.0/depth_anything_v2_vitl.onnx"
        ),
        input_size=518,
        size_label="约 1.3 GB",
        expected_bytes=1_337_282_560,
    ),
)

CUSTOM_MODEL_ID = "custom"


def depth_models_dir() -> Path:
    import sys

    from app.utils.constants import APP_NAME, APP_ORG, project_root

    if getattr(sys, "frozen", False):
        from PySide6.QtCore import QStandardPaths

        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        )
        if base:
            return Path(base) / "depth_models"
        return Path.home() / APP_ORG / APP_NAME / "depth_models"
    return project_root() / "models" / "depth"


def spec_by_id(model_id: str) -> DepthModelSpec | None:
    for spec in DEPTH_MODELS:
        if spec.model_id == model_id:
            return spec
    return None
