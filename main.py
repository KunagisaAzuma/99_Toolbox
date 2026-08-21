"""工具箱入口."""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from app.toolbox_window import ToolboxWindow
from app.utils.constants import APP_NAME, APP_ORG


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    window = ToolboxWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
