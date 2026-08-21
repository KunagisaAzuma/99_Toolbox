"""音轨列表与视频分组组件."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models import AudioTrackInfo, FileGroupStatus, VideoFileInfo
from app.utils.helpers import (
    channel_layout_display,
    format_bitrate,
    format_duration,
    format_file_size,
    language_display,
)

from .track_card import TrackCard

STATUS_TEXT = {
    FileGroupStatus.READY: "就绪",
    FileGroupStatus.PARSING: "解析中",
    FileGroupStatus.DONE: "完成",
    FileGroupStatus.FAILED: "失败",
    FileGroupStatus.EXTRACTING: "提取中",
}


def _track_summary(track: AudioTrackInfo) -> str:
    category = "无损" if track.codec_category == "lossless" else "有损"
    parts = [
        f"{track.codec_name.upper()}({category})",
        channel_layout_display(track.channels, track.channel_layout),
        language_display(track.language),
        format_bitrate(track.bit_rate),
    ]
    if track.sample_rate:
        parts.insert(3, f"{track.sample_rate} Hz")
    return " · ".join(parts)


class TrackListWidget(QWidget):
    """单视频页面使用的音轨列表（含独立滚动）."""

    selection_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self._cards: list[TrackCard] = []
        self._empty_label = QLabel("该视频不包含任何音频轨道")
        self._empty_label.hide()
        self.list_layout.insertWidget(0, self._empty_label)

    def clear(self) -> None:
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()
        self._empty_label.hide()

    def render_tracks(self, tracks: list[AudioTrackInfo]) -> None:
        self.clear()
        if not tracks:
            self._empty_label.show()
            self.selection_changed.emit()
            return
        self._empty_label.hide()
        for track in tracks:
            card = TrackCard(track)
            card.selection_changed.connect(self.selection_changed.emit)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)
            self._cards.append(card)
        self.selection_changed.emit()

    def selected_tracks(self) -> list[AudioTrackInfo]:
        return [c.track for c in self._cards if c.is_selected()]

    def all_tracks(self) -> list[AudioTrackInfo]:
        return [c.track for c in self._cards]

    def set_all_selected(self, checked: bool) -> None:
        for card in self._cards:
            card.set_selected(checked)
        self.selection_changed.emit()

    def is_all_selected(self) -> bool:
        return bool(self._cards) and all(c.is_selected() for c in self._cards)

    def set_mp3_mode(self, enabled: bool) -> None:
        for card in self._cards:
            card.set_mp3_mode(enabled)

    @property
    def cards(self) -> list[TrackCard]:
        return list(self._cards)


class CompactTrackRow(QWidget):
    """批量列表内的紧凑音轨行."""

    selection_changed = Signal()

    def __init__(self, track: AudioTrackInfo, parent=None) -> None:
        super().__init__(parent)
        self.track = track
        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 2, 4, 2)
        layout.setSpacing(8)

        self.checkbox = QCheckBox(f"#{track.index + 1}")
        self.checkbox.setChecked(track.default_selected)
        self.checkbox.setMinimumWidth(48)
        self.checkbox.stateChanged.connect(lambda _=None: self.selection_changed.emit())
        layout.addWidget(self.checkbox)

        self.info_label = QLabel(_track_summary(track))
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.info_label, 1)

        self.mp3_hint = QLabel("→ MP3")
        self.mp3_hint.setVisible(False)
        layout.addWidget(self.mp3_hint)

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()

    def set_selected(self, checked: bool) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)

    def set_mp3_mode(self, enabled: bool) -> None:
        self.mp3_hint.setVisible(enabled)


class VideoFileGroup(QFrame):
    """批量处理：扁平行布局，左侧勾选，便于快速选择."""

    remove_requested = Signal(str)
    selection_changed = Signal()

    def __init__(self, file_path: str, parent=None) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.video: VideoFileInfo | None = None
        self.status = FileGroupStatus.PARSING
        self._expanded = False
        self._mp3_mode = False
        self._track_rows: list[CompactTrackRow] = []
        self._updating_checks = False

        self.setFrameShape(QFrame.Shape.NoFrame)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(4, 4, 4, 4)
        header.setSpacing(8)

        self.file_check = QCheckBox()
        self.file_check.setTristate(True)
        self.file_check.setToolTip("勾选/取消本文件全部音轨")
        self.file_check.setEnabled(False)
        self.file_check.stateChanged.connect(self._on_file_check_changed)
        header.addWidget(self.file_check)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_btn.setAutoRaise(True)
        self.toggle_btn.setFixedSize(20, 20)
        self.toggle_btn.setVisible(False)
        self.toggle_btn.clicked.connect(self._toggle)
        header.addWidget(self.toggle_btn)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(Path(file_path).name)
        title_font = QFont(self.title_label.font())
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.title_label.setToolTip(file_path)
        text_col.addWidget(self.title_label)

        self.meta_label = QLabel("解析中…")
        self.meta_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_col.addWidget(self.meta_label)
        header.addLayout(text_col, 1)

        self.status_label = QLabel(STATUS_TEXT[self.status])
        self.status_label.setFixedWidth(48)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.status_label)

        self.progress_label = QLabel("")
        header.addWidget(self.progress_label)

        remove_btn = QToolButton()
        remove_btn.setText("✕")
        remove_btn.setAutoRaise(True)
        remove_btn.setToolTip("移除此文件")
        remove_btn.setFixedSize(24, 24)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.file_path))
        header.addWidget(remove_btn)
        root.addLayout(header)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 4)
        self.content_layout.setSpacing(0)
        self.content.setVisible(False)
        root.addWidget(self.content)

        self.error_label = QLabel("")
        self.error_label.hide()
        root.addWidget(self.error_label)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    def set_parsing(self) -> None:
        self.status = FileGroupStatus.PARSING
        self.status_label.setText(STATUS_TEXT[self.status])
        self.meta_label.setText("解析中…")
        self.file_check.setEnabled(False)

    def set_success(self, video: VideoFileInfo) -> None:
        self.video = video
        self.status = FileGroupStatus.READY
        self.status_label.setText(STATUS_TEXT[self.status])
        self.title_label.setText(video.file_name)
        self.title_label.setToolTip(video.file_path)
        self.error_label.hide()
        self._rebuild_tracks(video.audio_tracks)

    def set_failed(self, message: str) -> None:
        self.status = FileGroupStatus.FAILED
        self.status_label.setText(STATUS_TEXT[self.status])
        self.meta_label.setText(message)
        self.error_label.setText(message)
        self.error_label.show()
        self.file_check.setEnabled(False)
        self._clear_track_rows()
        self.toggle_btn.setVisible(False)
        self.content.setVisible(False)

    def set_extracting(self, done: int = 0, total: int = 0) -> None:
        self.status = FileGroupStatus.EXTRACTING
        self.status_label.setText(STATUS_TEXT[self.status])
        self.progress_label.setText(f"{done}/{total}" if total else "")

    def set_done(self, success: bool = True) -> None:
        self.status = FileGroupStatus.DONE if success else FileGroupStatus.FAILED
        self.status_label.setText(STATUS_TEXT[self.status])

    def _clear_track_rows(self) -> None:
        for row in self._track_rows:
            row.deleteLater()
        self._track_rows.clear()

    def _rebuild_tracks(self, tracks: list[AudioTrackInfo]) -> None:
        self._clear_track_rows()
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not tracks:
            self.meta_label.setText("无音轨")
            self.file_check.setEnabled(False)
            self.toggle_btn.setVisible(False)
            self.content.setVisible(False)
            self.selection_changed.emit()
            return

        size = format_file_size(self.video.file_size) if self.video else ""
        duration = format_duration(self.video.duration) if self.video else ""

        if len(tracks) == 1:
            # 单音轨：全部信息压在一行，勾选即选中该轨
            track = tracks[0]
            self.meta_label.setText(
                f"{_track_summary(track)}    {size} · {duration}"
            )
            self.toggle_btn.setVisible(False)
            self.content.setVisible(False)
            self._expanded = False
            self.file_check.setEnabled(True)
            self.file_check.setTristate(False)
            self._updating_checks = True
            self.file_check.setChecked(track.default_selected)
            self._updating_checks = False
            # 用隐藏行保存勾选状态，便于统一 API
            hidden = CompactTrackRow(track)
            hidden.set_selected(track.default_selected)
            hidden.hide()
            self.content_layout.addWidget(hidden)
            self._track_rows.append(hidden)
        else:
            self.meta_label.setText(f"{len(tracks)} 条音轨 · {size} · {duration}")
            self.toggle_btn.setVisible(True)
            self.file_check.setEnabled(True)
            self.file_check.setTristate(True)
            for track in tracks:
                row = CompactTrackRow(track)
                row.set_mp3_mode(self._mp3_mode)
                row.selection_changed.connect(self._on_track_changed)
                self.content_layout.addWidget(row)
                self._track_rows.append(row)
            self.set_expanded(False)
            self._sync_file_check_from_tracks()

        if self._mp3_mode and len(tracks) == 1:
            tip = self.meta_label.text()
            if "→ MP3" not in tip:
                self.meta_label.setText(tip + "  → MP3")
        self.selection_changed.emit()

    def set_expanded(self, expanded: bool) -> None:
        if not self.video or not self.video.audio_tracks or len(self.video.audio_tracks) <= 1:
            self._expanded = False
            self.content.setVisible(False)
            self.toggle_btn.setVisible(bool(self.video and self.video.track_count > 1))
            self.toggle_btn.setArrowType(Qt.ArrowType.RightArrow)
            return
        self._expanded = expanded
        self.content.setVisible(expanded)
        self.toggle_btn.setVisible(True)
        self.toggle_btn.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def _toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def _on_file_check_changed(self, state: int) -> None:
        if self._updating_checks:
            return
        if not self._track_rows:
            return
        # 三态下 PartiallyChecked 点击会到 Checked；这里把任意非 Unchecked 视为全选
        checked = state != Qt.CheckState.Unchecked.value
        self._updating_checks = True
        for row in self._track_rows:
            row.set_selected(checked)
        if self.file_check.isTristate():
            self.file_check.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
        self._updating_checks = False
        self.selection_changed.emit()

    def _on_track_changed(self) -> None:
        self._sync_file_check_from_tracks()
        self.selection_changed.emit()

    def _sync_file_check_from_tracks(self) -> None:
        if not self._track_rows:
            return
        selected = sum(1 for r in self._track_rows if r.is_selected())
        total = len(self._track_rows)
        self._updating_checks = True
        if selected == 0:
            self.file_check.setCheckState(Qt.CheckState.Unchecked)
        elif selected == total:
            self.file_check.setCheckState(Qt.CheckState.Checked)
        else:
            self.file_check.setCheckState(Qt.CheckState.PartiallyChecked)
        self._updating_checks = False

    def selected_tracks(self) -> list[AudioTrackInfo]:
        return [r.track for r in self._track_rows if r.is_selected()]

    def set_all_selected(self, checked: bool) -> None:
        if not self._track_rows:
            return
        self._updating_checks = True
        for row in self._track_rows:
            row.set_selected(checked)
        self.file_check.setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self._updating_checks = False
        self.selection_changed.emit()

    def set_mp3_mode(self, enabled: bool) -> None:
        self._mp3_mode = enabled
        for row in self._track_rows:
            row.set_mp3_mode(enabled)
        if self.video and len(self.video.audio_tracks) == 1 and self.video.audio_tracks:
            track = self.video.audio_tracks[0]
            size = format_file_size(self.video.file_size)
            duration = format_duration(self.video.duration)
            text = f"{_track_summary(track)}    {size} · {duration}"
            if enabled:
                text += "  → MP3"
            self.meta_label.setText(text)


class VideoFileGroupList(QWidget):
    selection_changed = Signal()
    remove_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self._groups: dict[str, VideoFileGroup] = {}

    def clear(self) -> None:
        for group in self._groups.values():
            group.deleteLater()
        self._groups.clear()
        self.selection_changed.emit()

    def add_group(self, file_path: str) -> VideoFileGroup:
        if file_path in self._groups:
            return self._groups[file_path]
        group = VideoFileGroup(file_path)
        group.remove_requested.connect(self.remove_requested.emit)
        group.selection_changed.connect(self.selection_changed.emit)
        index = self.list_layout.count() - 1
        self.list_layout.insertWidget(index, group)
        self._groups[file_path] = group
        return group

    def remove_group(self, file_path: str) -> None:
        group = self._groups.pop(file_path, None)
        if group:
            group.deleteLater()
            self.selection_changed.emit()

    def get_group(self, file_path: str) -> VideoFileGroup | None:
        return self._groups.get(file_path)

    def groups(self) -> list[VideoFileGroup]:
        return list(self._groups.values())

    def expand_all(self) -> None:
        for group in self._groups.values():
            group.set_expanded(True)

    def collapse_all(self) -> None:
        for group in self._groups.values():
            group.set_expanded(False)

    def set_all_selected(self, checked: bool) -> None:
        for group in self._groups.values():
            group.set_all_selected(checked)
        self.selection_changed.emit()

    def set_mp3_mode(self, enabled: bool) -> None:
        for group in self._groups.values():
            group.set_mp3_mode(enabled)

    def total_tracks(self) -> int:
        total = 0
        for group in self._groups.values():
            if group.video:
                total += group.video.track_count
        return total

    def has_any_selection(self) -> bool:
        return any(group.selected_tracks() for group in self._groups.values())

    def has_any_video_track(self) -> bool:
        return any(group.video and group.video.has_video for group in self._groups.values())
