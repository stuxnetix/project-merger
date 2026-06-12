"""Dialog for editing gitignore rules."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from config import DEFAULT_GITIGNORE_PATTERNS


class RulesDialog(QDialog):
    def __init__(self, patterns: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Правила исключений")
        self.resize(500, 440)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Шаблон правил для исключения файлов и папок:"))

        self.list_widget = QListWidget()
        self.list_widget.addItems(patterns)
        layout.addWidget(self.list_widget)

        add_layout = QHBoxLayout()
        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText("Новое правило (например, *.log или temp/)")
        self.add_input.returnPressed.connect(self._add_rule)
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_rule)
        add_layout.addWidget(self.add_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        actions_layout = QHBoxLayout()
        remove_btn = QPushButton("Удалить выбранное")
        remove_btn.clicked.connect(self._remove_selected)
        reset_btn = QPushButton("Сбросить к стандартным")
        reset_btn.clicked.connect(self._reset_to_defaults)
        actions_layout.addWidget(remove_btn)
        actions_layout.addWidget(reset_btn)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _add_rule(self) -> None:
        text = self.add_input.text().strip()
        if not text:
            return
        items = {self.list_widget.item(i).text() for i in range(self.list_widget.count())}
        if text not in items:
            self.list_widget.addItem(text)
        self.add_input.clear()

    def _remove_selected(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def _reset_to_defaults(self) -> None:
        reply = QMessageBox.question(
            self,
            "Сбросить правила",
            "Заменить текущий список стандартным набором правил?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.list_widget.clear()
            self.list_widget.addItems(DEFAULT_GITIGNORE_PATTERNS)

    def get_patterns(self) -> list[str]:
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
