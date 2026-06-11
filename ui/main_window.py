"""Main application window."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import Config
from gitignore_handler import create_default_gitignore, get_combined_spec, get_gitignore_spec
from ui.rules_dialog import RulesDialog
from ui.workers import MergerWorker

logger = logging.getLogger(__name__)

TREE_STYLE = """
QTreeWidget {
    font-size: 13px;
    font-family: "Segoe UI", system-ui, sans-serif;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
    alternate-background-color: #F8F9FA;
    outline: none;
}
QTreeWidget::item {
    padding: 4px 6px;
    border-radius: 4px;
}
QTreeWidget::item:selected {
    background-color: #E3F2FD;
    color: #1565C0;
}
QTreeWidget::item:hover {
    background-color: #F0F0F0;
}
QTreeWidget::branch:has-children:!has-siblings:closed-adjoins-item {
    border-image: none;
}
QHeaderView::section {
    background-color: #F5F5F5;
    border: none;
    padding: 6px;
    font-weight: 600;
}
"""

BTN_STYLE = """
QPushButton {
    background-color: #1976D2;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    font-family: "Segoe UI", system-ui, sans-serif;
}
QPushButton:hover {
    background-color: #1565C0;
}
QPushButton:pressed {
    background-color: #0D47A1;
}
QPushButton:disabled {
    background-color: #BDBDBD;
    color: #757575;
}
"""

SECONDARY_BTN_STYLE = """
QPushButton {
    background-color: #FFFFFF;
    color: #1976D2;
    border: 1px solid #1976D2;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    font-family: "Segoe UI", system-ui, sans-serif;
}
QPushButton:hover {
    background-color: #E3F2FD;
}
QPushButton:pressed {
    background-color: #BBDEFB;
}
QPushButton:disabled {
    border-color: #BDBDBD;
    color: #BDBDBD;
}
"""


class DropZone(QWidget):
    directory_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon = QLabel("📂")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 56px;")

        plus = QLabel("+")
        plus.setAlignment(Qt.AlignCenter)
        plus.setStyleSheet("font-size: 40px; color: #64B5F6; font-weight: 300; margin-top: -8px;")

        text = QLabel("Перетащите проект сюда\nили нажмите чтобы открыть")
        text.setAlignment(Qt.AlignCenter)
        text.setStyleSheet("font-size: 15px; color: #546E7A; font-family: 'Segoe UI', system-ui, sans-serif;")

        layout.addWidget(icon)
        layout.addWidget(plus)
        layout.addWidget(text)

        self.setStyleSheet("""
            DropZone {
                background-color: #E3F2FD;
                border: 2px dashed #90CAF9;
                border-radius: 16px;
            }
            DropZone:hover {
                background-color: #BBDEFB;
                border-color: #64B5F6;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.is_dir():
                self.directory_selected.emit(str(path))

    def mousePressEvent(self, event) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "Выберите папку проекта")
        if dir_path:
            self.directory_selected.emit(dir_path)


class MainWindow(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.root_path: Path | None = None
        self.spec = None
        self.combined_spec = None
        self.selected_paths: set[Path] = set()
        self.worker: MergerWorker | None = None
        self._scan_count = 0
        self._scan_cancelled = False

        self.setWindowTitle("Project Merger")
        self.resize(900, 700)
        self.setAcceptDrops(True)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        self.stack = QStackedWidget()

        # Page 0 — drag & drop zone
        self.drop_zone = DropZone()
        self.drop_zone.directory_selected.connect(self._load_project)
        self.stack.addWidget(self.drop_zone)

        # Page 1 — project tree + controls
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.folder_icon = QLabel("📁")
        self.folder_icon.setStyleSheet("font-size: 18px;")

        self.folder_label = QLabel("Проект не выбран")
        self.folder_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                font-family: 'Segoe UI', system-ui, sans-serif;
                color: #212121;
                padding: 4px 0;
            }
        """)

        self.change_folder_btn = QPushButton("Открыть другой проект")
        self.change_folder_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #1976D2;
                font-size: 13px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                padding: 4px 8px;
            }
            QPushButton:hover {
                color: #0D47A1;
                text-decoration: underline;
            }
        """)
        self.change_folder_btn.clicked.connect(self._choose_folder)

        self.exit_btn = QPushButton("✕ Выход")
        self.exit_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #757575;
                font-size: 13px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                padding: 4px 8px;
            }
            QPushButton:hover {
                color: #D32F2F;
            }
        """)
        self.exit_btn.clicked.connect(self.close)

        top_layout.addWidget(self.folder_icon)
        top_layout.addWidget(self.folder_label)
        top_layout.addStretch()
        top_layout.addWidget(self.change_folder_btn)
        top_layout.addWidget(self.exit_btn)
        content_layout.addLayout(top_layout)

        self.tree_stack = QStackedWidget()

        loading_page = QWidget()
        loading_layout = QVBoxLayout(loading_page)
        loading_layout.setAlignment(Qt.AlignCenter)
        loading_layout.setSpacing(20)

        self.loading_label = QLabel("⏳  Сканирование файловой системы...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("""
            QLabel {
                font-size: 17px;
                color: #1976D2;
                font-family: 'Segoe UI', system-ui, sans-serif;
                background: #F5F5F5;
                border-radius: 8px;
                padding: 40px;
            }
        """)
        loading_layout.addWidget(self.loading_label)

        self.cancel_scan_btn = QPushButton("✕ Отменить сканирование")
        self.cancel_scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #D32F2F;
                border: 1px solid #D32F2F;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QPushButton:hover {
                background-color: #FFEBEE;
            }
        """)
        self.cancel_scan_btn.clicked.connect(self._cancel_scan)
        loading_layout.addWidget(self.cancel_scan_btn, alignment=Qt.AlignCenter)

        self.tree_stack.addWidget(loading_page)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Файлы и папки"])
        self.tree.header().setSectionResizeMode(QHeaderView.Stretch)
        self.tree.header().setVisible(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(20)
        self.tree.setStyleSheet(TREE_STYLE)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree_stack.addWidget(self.tree)

        self.tree_stack.setCurrentIndex(1)
        content_layout.addWidget(self.tree_stack)

        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("✓ Выделить всё")
        self.select_all_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn = QPushButton("✕ Снять всё")
        self.deselect_all_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.update_gitignore_btn = QPushButton("Обновить .gitignore")
        self.update_gitignore_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        self.update_gitignore_btn.clicked.connect(self._update_gitignore)
        self.rules_btn = QPushButton("Правила")
        self.rules_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        self.rules_btn.clicked.connect(self._edit_rules)
        self.merge_all_btn = QPushButton("Собрать весь проект")
        self.merge_all_btn.setStyleSheet(BTN_STYLE)
        self.merge_all_btn.clicked.connect(self._merge_all)
        self.merge_selected_btn = QPushButton("Собрать выбранное")
        self.merge_selected_btn.setStyleSheet(BTN_STYLE)
        self.merge_selected_btn.clicked.connect(self._merge_selected)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addWidget(self.update_gitignore_btn)
        btn_layout.addWidget(self.rules_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.merge_all_btn)
        btn_layout.addWidget(self.merge_selected_btn)
        content_layout.addLayout(btn_layout)

        self.stack.addWidget(content)
        main_layout.addWidget(self.stack)

        self.statusBar().showMessage("Готов")
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background: #F5F5F5;
                border-top: 1px solid #E0E0E0;
                font-size: 12px;
                color: #757575;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
        """)

        self.stack.setCurrentIndex(0)
        self._update_buttons()

    # ───────── Drag & drop on the whole window ─────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.is_dir():
                self._load_project(str(path))

    # ───────── Project loading ─────────

    def _load_project(self, dir_path: str) -> None:
        self.root_path = Path(dir_path)
        self.config.last_source_dir = str(self.root_path)
        self.folder_label.setText(str(self.root_path))

        spec = get_gitignore_spec(self.root_path)
        if spec is None:
            reply = QMessageBox.question(
                self,
                ".gitignore не найден",
                "Файл .gitignore отсутствует. Создать его с типовыми исключениями?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                created = create_default_gitignore(
                    self.root_path, self.config.default_gitignore_patterns
                )
                if created:
                    spec = get_gitignore_spec(self.root_path)
        self.spec = spec
        self.combined_spec = get_combined_spec(self.root_path, self.config.default_gitignore_patterns)
        self.stack.setCurrentIndex(1)
        self.tree_stack.setCurrentIndex(0)
        self.statusBar().showMessage("Сканирование файлов...")
        QApplication.processEvents()
        self._populate_tree()
        self.tree_stack.setCurrentIndex(1)
        self.statusBar().showMessage(f"Загружен проект: {self.root_path}")

    def _choose_folder(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "Выберите корневую папку проекта", self.config.last_source_dir
        )
        if not dir_path:
            return
        self._load_project(dir_path)

    # ───────── Tree population ─────────

    def _cancel_scan(self) -> None:
        self._scan_cancelled = True
        self.statusBar().showMessage("Сканирование отменено")
        self.stack.setCurrentIndex(0)

    def closeEvent(self, event) -> None:
        self._scan_cancelled = True
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(3000)
        event.accept()

    def _populate_tree(self) -> None:
        if self.root_path is None:
            return
        self.tree.clear()
        self.selected_paths.clear()
        self._scan_count = 0
        self._scan_cancelled = False
        self.tree.setUpdatesEnabled(False)
        try:
            root_item = QTreeWidgetItem(self.tree, [self.root_path.name])
            root_item.setData(0, Qt.UserRole, self.root_path)
            root_item.setIcon(0, QApplication.style().standardIcon(QStyle.SP_DirOpenIcon))
            self._add_subtree(root_item, self.root_path)
            if self._scan_cancelled:
                return
            root_item.setExpanded(True)

            self.tree.blockSignals(True)
            self._set_check_state(root_item, Qt.Checked)
            self._uncheck_ignored()
            self.tree.blockSignals(False)
        finally:
            self.tree.setUpdatesEnabled(True)

    def _uncheck_ignored(self) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            self._uncheck_recursive(root.child(i))

    def _uncheck_recursive(self, item: QTreeWidgetItem) -> None:
        if self._scan_cancelled:
            return
        entry: Path = item.data(0, Qt.UserRole)
        if entry:
            rel = entry.relative_to(self.root_path)
            check_path = str(rel) + ("/" if entry.is_dir() else "")
            if self.combined_spec and self.combined_spec.match_file(check_path):
                self._set_check_state(item, Qt.Unchecked)
                self._update_parent_states(item)
                return
        for i in range(item.childCount()):
            self._uncheck_recursive(item.child(i))

    def _add_subtree(self, parent_item: QTreeWidgetItem, directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return

        for entry in entries:
            if self._scan_cancelled:
                return
            if entry.name in (".git", ".gitignore"):
                continue

            rel = entry.relative_to(self.root_path)
            check_path = str(rel) + ("/" if entry.is_dir() else "")
            if self.combined_spec and self.combined_spec.match_file(check_path):
                continue

            self._scan_count += 1
            if self._scan_count % 30 == 0:
                self.statusBar().showMessage(f"Сканирование: {rel}  ({self._scan_count})")
                QApplication.processEvents()

            item = QTreeWidgetItem(parent_item)
            item.setText(0, entry.name)
            item.setData(0, Qt.UserRole, entry)
            item.setFlags(
                item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate
            )
            item.setCheckState(0, Qt.Unchecked)

            if entry.is_dir():
                item.setIcon(0, QApplication.style().standardIcon(QStyle.SP_DirIcon))
                self._add_subtree(item, entry)
            else:
                item.setIcon(0, QApplication.style().standardIcon(QStyle.SP_FileIcon))

    def _set_check_state(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        item.setCheckState(0, state)
        self._update_selected(item)
        for i in range(item.childCount()):
            self._set_check_state(item.child(i), state)

    def _update_selected(self, item: QTreeWidgetItem) -> None:
        entry: Path = item.data(0, Qt.UserRole)
        if entry is None:
            return
        rel = entry.relative_to(self.root_path)
        if item.checkState(0) == Qt.Checked:
            if entry.is_file():
                self.selected_paths.add(rel)
        else:
            self.selected_paths.discard(rel)
            for child in self._get_all_items(item):
                child_entry = child.data(0, Qt.UserRole)
                if child_entry and child_entry.is_file():
                    self.selected_paths.discard(
                        child_entry.relative_to(self.root_path)
                    )

    def _get_all_items(self, item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
        result = []
        for i in range(item.childCount()):
            child = item.child(i)
            result.append(child)
            result.extend(self._get_all_items(child))
        return result

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        self.tree.blockSignals(True)
        state = item.checkState(0)
        if state != Qt.PartiallyChecked:
            self._set_check_state(item, state)
        self._update_parent_states(item)
        self.tree.blockSignals(False)
        self._update_buttons()

    def _update_parent_states(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        while parent:
            checked = 0
            unchecked = 0
            for i in range(parent.childCount()):
                child_state = parent.child(i).checkState(0)
                if child_state == Qt.Checked:
                    checked += 1
                elif child_state == Qt.Unchecked:
                    unchecked += 1
            if checked == parent.childCount():
                parent.setCheckState(0, Qt.Checked)
            elif unchecked == parent.childCount():
                parent.setCheckState(0, Qt.Unchecked)
            else:
                parent.setCheckState(0, Qt.PartiallyChecked)
            parent = parent.parent()

    def _collect_selected_files(self) -> set[Path]:
        selected = set()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            self._collect_from_item(root.child(i), selected)
        return selected

    def _collect_from_item(self, item: QTreeWidgetItem, selected: set[Path]) -> None:
        entry: Path = item.data(0, Qt.UserRole)
        if entry and entry.is_file() and item.checkState(0) == Qt.Checked:
            selected.add(entry.relative_to(self.root_path))
        for i in range(item.childCount()):
            self._collect_from_item(item.child(i), selected)

    def _select_all(self) -> None:
        root = self.tree.invisibleRootItem()
        if root.childCount() > 0:
            self.tree.blockSignals(True)
            self._set_check_state(root.child(0), Qt.Checked)
            self._update_parent_states(root.child(0))
            self.tree.blockSignals(False)

    def _deselect_all(self) -> None:
        root = self.tree.invisibleRootItem()
        if root.childCount() > 0:
            self.tree.blockSignals(True)
            self._set_check_state(root.child(0), Qt.Unchecked)
            self._update_parent_states(root.child(0))
            self.tree.blockSignals(False)

    def _merge_all(self) -> None:
        self.selected_paths = set()
        self._run_merger(spec=self.combined_spec)

    def _merge_selected(self) -> None:
        self.selected_paths = self._collect_selected_files()
        if not self.selected_paths:
            QMessageBox.warning(self, "Нет файлов", "Не выбрано ни одного файла.")
            return
        self._run_merger(spec=None)

    def _run_merger(self, spec=None) -> None:
        if self.root_path is None:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку проекта.")
            return

        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Занято", "Генерация уже выполняется. Дождитесь завершения.")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить project_merged.md",
            str(Path(self.config.last_output_dir) / "project_merged.md"),
            "Markdown (*.md)",
        )
        if not save_path:
            return
        output = Path(save_path)
        self.config.last_output_dir = str(output.parent)
        self.config.save()

        self.statusBar().showMessage("Сборка проекта...")
        self._set_merge_buttons_enabled(False)
        self.worker = MergerWorker(self.root_path, spec, self.selected_paths, output)
        self.worker.finished.connect(self._on_merge_finished)
        self.worker.error.connect(self._on_merge_error)
        self.worker.start()

    def _set_merge_buttons_enabled(self, enabled: bool) -> None:
        self.merge_all_btn.setEnabled(enabled)
        self.merge_selected_btn.setEnabled(enabled)

    def _on_merge_finished(self, file_count: int) -> None:
        self._set_merge_buttons_enabled(True)
        self.statusBar().showMessage(f"Готово. Обработано файлов: {file_count}")
        QMessageBox.information(self, "Успех", f"Файл сохранён.\nФайлов обработано: {file_count}")

    def _on_merge_error(self, message: str) -> None:
        self._set_merge_buttons_enabled(True)
        self.statusBar().showMessage("Ошибка")
        QMessageBox.critical(self, "Ошибка", message)

    def _update_gitignore(self) -> None:
        if self.root_path is None:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку проекта.")
            return

        gitignore_path = self.root_path / ".gitignore"
        if not gitignore_path.is_file():
            QMessageBox.warning(self, "Файл не найден", ".gitignore отсутствует в корне проекта.")
            return

        existing_patterns: set[str] = set()
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        existing_patterns.add(stripped)
        except OSError as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать .gitignore:\n{e}")
            return

        new_patterns = [
            p for p in self.config.default_gitignore_patterns
            if p not in existing_patterns
        ]
        if not new_patterns:
            QMessageBox.information(self, "Готово", "Все правила из шаблона уже присутствуют в .gitignore.")
            return

        try:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\n# Добавлено Project Merger\n")
                for pattern in new_patterns:
                    f.write(f"{pattern}\n")
        except OSError as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось записать .gitignore:\n{e}")
            return

        self.spec = get_gitignore_spec(self.root_path)
        self.combined_spec = get_combined_spec(self.root_path, self.config.default_gitignore_patterns)
        self._populate_tree()
        self.statusBar().showMessage(".gitignore обновлён")
        QMessageBox.information(
            self, "Готово",
            f"Добавлены правила исключений в .gitignore ({len(new_patterns)} шт.)."
        )

    def _edit_rules(self) -> None:
        dialog = RulesDialog(self.config.default_gitignore_patterns, self)
        if dialog.exec() != RulesDialog.Accepted:
            return
        new_patterns = dialog.get_patterns()
        self.config.data["default_gitignore"] = new_patterns
        self.config.save()
        if self.root_path is not None:
            self.combined_spec = get_combined_spec(self.root_path, new_patterns)
            self._populate_tree()
            self.statusBar().showMessage("Правила обновлены")

    def _update_buttons(self) -> None:
        enabled = self.root_path is not None
        self.select_all_btn.setEnabled(enabled)
        self.deselect_all_btn.setEnabled(enabled)
        self.merge_all_btn.setEnabled(enabled)
        self.merge_selected_btn.setEnabled(enabled)
        self.update_gitignore_btn.setEnabled(enabled)
        self.rules_btn.setEnabled(enabled)
