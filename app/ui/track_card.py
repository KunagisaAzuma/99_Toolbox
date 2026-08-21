"""音轨卡片组件."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models import AudioTrackInfo
from app.utils.helpers import (
    channel_layout_display,
    format_bitrate,
    language_display,
)


class TrackCard(QFrame):
    selection_changed = Signal()

    def __init__(self, track: AudioTrackInfo, parent=None) -> None:
        super().__init__(parent)
        self.track = track
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        row = QHBoxLayout()
        self.checkbox = QCheckBox(f"音轨 #{track.index + 1}")
        self.checkbox.setChecked(track.default_selected)
        self.checkbox.stateChanged.connect(lambda _=None: self.selection_changed.emit())
        row.addWidget(self.checkbox)

        category = "无损" if track.codec_category == "lossless" else "有损"
        self.codec_label = QLabel(f"{track.codec_name.upper()} ({category})")
        row.addWidget(self.codec_label)

        row.addWidget(QLabel(channel_layout_display(track.channels, track.channel_layout)))
        row.addWidget(QLabel(language_display(track.language)))

        rate_parts = []
        if track.sample_rate:
            rate_parts.append(f"{track.sample_rate} Hz")
        rate_parts.append(format_bitrate(track.bit_rate))
        row.addWidget(QLabel(" · ".join(rate_parts)))

        self.mp3_hint = QLabel("→ .mp3")
        self.mp3_hint.setVisible(False)
        row.addWidget(self.mp3_hint)

        row.addStretch(1)

        self.expand_btn = QPushButton("▼")
        self.expand_btn.setFixedWidth(32)
        self.expand_btn.setFlat(True)
        self.expand_btn.clicked.connect(self._toggle_detail)
        row.addWidget(self.expand_btn)
        root.addLayout(row)

        self.detail = QWidget()
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(28, 0, 0, 0)
        detail_lines = [
            f"编码器: {track.codec_long_name}",
            f"Profile: {track.profile or '—'}",
            f"帧数: {track.frames if track.frames is not None else '—'}",
            f"时长: {track.duration:.2f}s" if track.duration else "时长: —",
            f"标题: {track.title or '—'}",
        ]
        if track.tags:
            tags_preview = ", ".join(f"{k}={v}" for k, v in list(track.tags.items())[:6])
            detail_lines.append(f"Tags: {tags_preview}")
        for line in detail_lines:
            label = QLabel(line)
            detail_layout.addWidget(label)
        self.detail.setVisible(False)
        root.addWidget(self.detail)

        self._expanded = False

    def _toggle_detail(self) -> None:
        self._expanded = not self._expanded
        self.detail.setVisible(self._expanded)
        self.expand_btn.setText("▲" if self._expanded else "▼")

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()

    def set_selected(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)

    def set_mp3_mode(self, enabled: bool) -> None:
        self.mp3_hint.setVisible(enabled)
        if enabled and self.track.codec_category == "lossless":
            self.mp3_hint.setToolTip("将无损音频转为 MP3 将丢失部分音频信息")
        else:
            self.mp3_hint.setToolTip("")
