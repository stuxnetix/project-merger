"""Dialog for editing gitignore rules."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)


class RulesDialog(QDialog):
    def __init__(self, patterns: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Правила .gitignore")
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Шаблон правил для исключения файлов и папок:"))

        self.list_widget = QListWidget()
        self.list_widget.addItems(patterns)
        layout.addWidget(self.list_widget)

        add_layout = QHBoxLayout()
        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText("Новое правило (например, *.log или temp/)")
        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self._add_rule)
        add_layout.addWidget(self.add_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        remove_btn = QPushButton("Удалить выбранное")
        remove_btn.clicked.connect(self._remove_selected)
        layout.addWidget(remove_btn)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
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
        items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        if text not in items:
            self.list_widget.addItem(text)
        self.add_input.clear()

    def _remove_selected(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def get_patterns(self) -> list[str]:
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
