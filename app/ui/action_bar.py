"""操作按钮栏."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QPushButton, QWidget


class ActionBar(QWidget):
    select_all_toggled = Signal(bool)
    extract_selected = Signal()
    extract_all = Signal()
    cancel_requested = Signal()

    def __init__(self, batch_mode: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._batch_mode = batch_mode
        self._extracting = False
        self._all_selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.select_all_btn = QPushButton("全部全选" if batch_mode else "全选")
        self.select_all_btn.setCheckable(True)
        self.select_all_btn.clicked.connect(self._on_select_all)
        layout.addWidget(self.select_all_btn)

        self.extract_selected_btn = QPushButton(
            "批量提取选中的音轨" if batch_mode else "提取选中的音轨"
        )
        self.extract_selected_btn.clicked.connect(self.extract_selected.emit)
        layout.addWidget(self.extract_selected_btn)

        self.extract_all_btn = QPushButton("提取全部音轨")
        self.extract_all_btn.clicked.connect(self.extract_all.emit)
        layout.addWidget(self.extract_all_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        self.cancel_btn.setVisible(False)
        layout.addWidget(self.cancel_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress, 1)

        self.set_idle_state()

    def _on_select_all(self, checked: bool) -> None:
        self._all_selected = checked
        self.select_all_btn.setText(
            ("取消全选" if self._batch_mode else "取消全选") if checked else (
                "全部全选" if self._batch_mode else "全选"
            )
        )
        self.select_all_toggled.emit(checked)

    def set_select_all_checked(self, checked: bool) -> None:
        self.select_all_btn.blockSignals(True)
        self.select_all_btn.setChecked(checked)
        self._all_selected = checked
        self.select_all_btn.setText(
            "取消全选" if checked else ("全部全选" if self._batch_mode else "全选")
        )
        self.select_all_btn.blockSignals(False)

    def set_idle_state(self) -> None:
        self._extracting = False
        self.select_all_btn.setEnabled(False)
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.extract_selected_btn.setVisible(True)
        self.extract_all_btn.setVisible(True)
        self.progress.setVisible(False)
        self.progress.setValue(0)

    def set_ready_state(
        self,
        has_tracks: bool,
        has_selection: bool,
        has_output_dir: bool,
        export_video_only: bool = False,
    ) -> None:
        if self._extracting:
            return
        self.select_all_btn.setEnabled(has_tracks)
        can_extract_selected = has_output_dir and (has_selection or export_video_only)
        can_extract_all = has_output_dir and has_tracks
        self.extract_selected_btn.setEnabled(can_extract_selected)
        self.extract_all_btn.setEnabled(can_extract_all)

    def set_extracting(self, extracting: bool) -> None:
        self._extracting = extracting
        self.select_all_btn.setEnabled(not extracting)
        self.extract_selected_btn.setVisible(not extracting)
        self.extract_all_btn.setVisible(not extracting)
        self.cancel_btn.setVisible(extracting)
        self.progress.setVisible(extracting)
        if not extracting:
            self.progress.setValue(0)

    def set_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0, min(100, value))))
