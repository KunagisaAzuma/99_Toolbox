"""选择要下载或删除的深度模型（系统原生，无 QSS）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.depth_models import DEPTH_MODELS, DepthModelSpec
from app.core.model_downloader import is_model_ready
from app.ui.model_download_dialog import ModelDownloadDialog
from app.utils.constants import DEPTH_TOOL_NAME

ROLE_MODEL_ID = Qt.ItemDataRole.UserRole


def _item_text(spec: DepthModelSpec, *, for_delete: bool) -> str:
    if for_delete:
        return f"{spec.speed_tag} · {spec.short_name}（{spec.size_label}）"
    status = "已下载" if is_model_ready(spec) else "未下载"
    return f"{spec.speed_tag} · {spec.short_name}（{spec.size_label}）[{status}]"


class ModelChoiceDialog(QDialog):
    def __init__(self, *, delete_mode: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._delete_mode = delete_mode
        self.setWindowTitle("删除模型" if delete_mode else "下载模型")
        self.setModal(True)
        self.resize(520, 320)

        layout = QVBoxLayout(self)
        if delete_mode:
            hint = "勾选要删除的已下载模型。"
        else:
            hint = "下列为全部受支持的深度图模型。勾选后下载；已下载项不可重复下载。"
        layout.addWidget(QLabel(hint))

        self.list = QListWidget()
        self._fill()
        layout.addWidget(self.list, 1)

        tools = QHBoxLayout()
        select_all = QPushButton("全选")
        select_all.clicked.connect(lambda: self._set_all(True))
        clear_all = QPushButton("全不选")
        clear_all.clicked.connect(lambda: self._set_all(False))
        tools.addWidget(select_all)
        tools.addWidget(clear_all)
        tools.addStretch(1)
        layout.addLayout(tools)

        buttons = QDialogButtonBox()
        ok_text = "删除所选" if delete_mode else "下载所选"
        self.ok_btn = buttons.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _fill(self) -> None:
        self.list.clear()
        specs = DEPTH_MODELS if not self._delete_mode else [s for s in DEPTH_MODELS if is_model_ready(s)]
        for spec in specs:
            item = QListWidgetItem(_item_text(spec, for_delete=self._delete_mode))
            item.setData(ROLE_MODEL_ID, spec.model_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            ready = is_model_ready(spec)
            if self._delete_mode:
                item.setCheckState(Qt.CheckState.Unchecked)
            elif ready:
                item.setCheckState(Qt.CheckState.Checked)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        if self.list.count() == 0:
            empty = QListWidgetItem("没有可删除的已下载模型")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
            self.ok_btn.setEnabled(False)

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.flags() & Qt.ItemFlag.ItemIsEnabled and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(state)

    def selected_specs(self) -> list[DepthModelSpec]:
        from app.core.depth_models import spec_by_id

        result: list[DepthModelSpec] = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                continue
            if item.checkState() != Qt.CheckState.Checked:
                continue
            spec = spec_by_id(str(item.data(ROLE_MODEL_ID) or ""))
            if spec:
                result.append(spec)
        return result

    def _accept(self) -> None:
        if not self.selected_specs():
            QMessageBox.information(self, self.windowTitle(), "请至少勾选一个模型")
            return
        self.accept()


def pick_models_to_download(parent: QWidget | None = None) -> list[DepthModelSpec] | None:
    parent = parent or QApplication.activeWindow()
    dialog = ModelChoiceDialog(delete_mode=False, parent=parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.selected_specs()


def pick_models_to_delete(parent: QWidget | None = None) -> list[DepthModelSpec] | None:
    parent = parent or QApplication.activeWindow()
    dialog = ModelChoiceDialog(delete_mode=True, parent=parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.selected_specs()


def download_selected_models(
    specs: list[DepthModelSpec],
    parent: QWidget | None = None,
) -> bool:
    pending = [spec for spec in specs if spec.url and not is_model_ready(spec)]
    if not pending:
        return True
    parent = parent or QApplication.activeWindow()
    progress = ModelDownloadDialog(pending, parent)
    return progress.exec() == QDialog.DialogCode.Accepted


def prompt_first_download(parent: QWidget | None = None) -> bool:
    """无本地模型时必须选择至少一个；已有模型时可直接进入。"""
    from app.core.model_downloader import any_model_ready

    parent = parent or QApplication.activeWindow()
    if any_model_ready():
        return True

    box = QMessageBox(parent)
    box.setWindowTitle(DEPTH_TOOL_NAME)
    box.setText("尚未下载深度图模型。请选择要下载的模型（已标明速度快 / 精度高）。")
    choose_btn = box.addButton("选择模型", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("退出", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(choose_btn)
    box.exec()
    if box.clickedButton() != choose_btn:
        return False

    selected = pick_models_to_download(parent)
    if not selected:
        return False
    if not download_selected_models(selected, parent):
        return False
    return any_model_ready()
