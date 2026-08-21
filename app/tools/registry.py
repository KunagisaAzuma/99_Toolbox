"""工具箱条目注册。后续新工具在 all_tools() 中追加即可。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    title: str
    factory: Callable[[], QWidget | None]


def create_depth_tool() -> QWidget | None:
    from PySide6.QtWidgets import QMessageBox

    from app.depth_window import DepthToolWindow
    from app.ui.model_choice_dialog import prompt_first_download

    try:
        import cv2  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError:
        QMessageBox.warning(
            None,
            "深度图生成",
            "未安装 OpenCV / ONNX Runtime。\n请先安装：opencv-python-headless、onnxruntime",
        )
        return None
    if not prompt_first_download():
        return None
    return DepthToolWindow()


def all_tools() -> list[ToolSpec]:
    from app.main_window import ExtractToolWindow

    return [
        ToolSpec("media_split", "音视频分离", ExtractToolWindow),
        ToolSpec("depth_map", "深度图生成（需要联网下载模型）", create_depth_tool),
    ]
