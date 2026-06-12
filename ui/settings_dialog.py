"""Application settings dialog: UI language, file size limit."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from i18n import tr


class SettingsDialog(QDialog):
    def __init__(self, language: str, max_file_size_kb: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel(tr("settings_language")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(tr("settings_lang_ru"), "ru")
        self.lang_combo.addItem(tr("settings_lang_en"), "en")
        self.lang_combo.setCurrentIndex(0 if language == "ru" else 1)
        layout.addWidget(self.lang_combo)

        layout.addSpacing(6)
        layout.addWidget(QLabel(tr("settings_size_limit")))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(0, 1024 * 100)  # up to 100 MB
        self.size_spin.setSingleStep(64)
        self.size_spin.setValue(max_file_size_kb)
        layout.addWidget(self.size_spin)

        hint = QLabel(tr("settings_size_hint"))
        hint.setStyleSheet("color: #757575; font-size: 12px;")
        layout.addWidget(hint)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(tr("ok"))
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(tr("cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def get_language(self) -> str:
        return self.lang_combo.currentData()

    def get_max_file_size_kb(self) -> int:
        return self.size_spin.value()
