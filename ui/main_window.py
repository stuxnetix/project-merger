"""Main application window."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon
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
from scanner import FsNode
from ui.rules_dialog import RulesDialog
from ui.workers import MergerWorker, ScanWorker

logger = logging.getLogger(__name__)

ROLE_REL_PATH = Qt.UserRole
ROLE_IS_DIR = Qt.UserRole + 1

PAGE_DROP = 0
PAGE_CONTENT = 1
TREE_PAGE_LOADING = 0
TREE_PAGE_TREE = 1

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
        self.combined_spec = None
        self.selected_paths: set[str] = set()
        self.scan_worker: ScanWorker | None = None
        self.merge_worker: MergerWorker | None = None

        self.setWindowTitle("Project Merger")
        self.resize(900, 700)
        self.setAcceptDrops(True)

        style = QApplication.style()
        self._dir_icon: QIcon = style.standardIcon(QStyle.SP_DirIcon)
        self._dir_open_icon: QIcon = style.standardIcon(QStyle.SP_DirOpenIcon)
        self._file_icon: QIcon = style.standardIcon(QStyle.SP_FileIcon)

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
        # Animations are O(visible items) per expand — disabled for large trees.
        self.tree.setAnimated(False)
        self.tree.setIndentation(20)
        self.tree.setStyleSheet(TREE_STYLE)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree_stack.addWidget(self.tree)

        self.tree_stack.setCurrentIndex(TREE_PAGE_TREE)
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

        self.stack.setCurrentIndex(PAGE_DROP)
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
        logger.info("Loading project: %s", dir_path)
        self._stop_scan_worker()

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
                create_default_gitignore(self.root_path, self.config.gitignore_patterns)

        self.combined_spec = get_combined_spec(self.root_path, self.config.gitignore_patterns)
        logger.info("Combined spec: %d patterns", len(self.combined_spec.patterns))

        self._start_scan()

    def _choose_folder(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "Выберите корневую папку проекта", self.config.last_source_dir
        )
        if not dir_path:
            return
        self._load_project(dir_path)

    # ───────── Scanning (background thread) ─────────

    def _start_scan(self) -> None:
        if self.root_path is None:
            return
        self._stop_scan_worker()

        self.stack.setCurrentIndex(PAGE_CONTENT)
        self.tree_stack.setCurrentIndex(TREE_PAGE_LOADING)
        self.loading_label.setText("⏳  Сканирование файловой системы...")
        self.statusBar().showMessage("Сканирование файлов...")
        self._set_controls_enabled(False)

        self.scan_worker = ScanWorker(self.root_path, self.combined_spec, parent=self)
        self.scan_worker.scan_done.connect(self._on_scan_done)
        self.scan_worker.scan_failed.connect(self._on_scan_failed)
        self.scan_worker.scan_progress.connect(self._on_scan_progress)
        self.scan_worker.start()

    def _stop_scan_worker(self) -> None:
        if self.scan_worker is not None:
            self.scan_worker.cancel()
            self.scan_worker.wait(5000)
            self.scan_worker = None

    def _cancel_scan(self) -> None:
        logger.info("Scan cancelled by user")
        self._stop_scan_worker()
        self.statusBar().showMessage("Сканирование отменено")
        self.stack.setCurrentIndex(PAGE_DROP)

    def _on_scan_progress(self, count: int, rel_path: str) -> None:
        self.loading_label.setText(f"⏳  Сканирование: {count} элементов...")
        self.statusBar().showMessage(f"Сканирование: {rel_path}  ({count})")

    def _on_scan_failed(self, message: str) -> None:
        self.scan_worker = None
        self._set_controls_enabled(True)
        self.statusBar().showMessage("Ошибка сканирования")
        self.stack.setCurrentIndex(PAGE_DROP)
        QMessageBox.critical(self, "Ошибка сканирования", message)

    def _on_scan_done(self, fs_root: FsNode, count: int) -> None:
        self.scan_worker = None
        self._populate_tree(fs_root)
        self.tree_stack.setCurrentIndex(TREE_PAGE_TREE)
        self._set_controls_enabled(True)
        self.statusBar().showMessage(f"Загружен проект: {self.root_path}  ({count} элементов)")

    # ───────── Tree population ─────────

    def _populate_tree(self, fs_root: FsNode) -> None:
        """Build the QTreeWidget from the scanned tree.

        Items are built detached and attached once; signals are blocked for the
        whole rebuild, so itemChanged never fires during population (this used
        to cause an O(n²) re-walk of the tree per added item).
        """
        self.tree.blockSignals(True)
        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()
            self.selected_paths.clear()

            root_item = QTreeWidgetItem([fs_root.name])
            root_item.setData(0, ROLE_REL_PATH, fs_root.rel_path)
            root_item.setData(0, ROLE_IS_DIR, True)
            root_item.setFlags(root_item.flags() | Qt.ItemIsUserCheckable)
            root_item.setCheckState(0, Qt.Checked)
            root_item.setIcon(0, self._dir_open_icon)
            self._build_items(root_item, fs_root)

            self.tree.addTopLevelItem(root_item)
            root_item.setExpanded(True)
            self._rebuild_selected()
        finally:
            self.tree.setUpdatesEnabled(True)
            self.tree.blockSignals(False)
        self._update_buttons()

    def _build_items(self, parent_item: QTreeWidgetItem, node: FsNode) -> None:
        for child in node.children:
            item = QTreeWidgetItem(parent_item, [child.name])
            item.setData(0, ROLE_REL_PATH, child.rel_path)
            item.setData(0, ROLE_IS_DIR, child.is_dir)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setIcon(0, self._dir_icon if child.is_dir else self._file_icon)
            if child.is_dir:
                self._build_items(item, child)

    # ───────── Selection handling ─────────

    def _set_check_state(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_check_state(item.child(i), state)

    def _rebuild_selected(self) -> None:
        self.selected_paths.clear()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            self._collect_from_item(root.child(i), self.selected_paths)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        self.tree.blockSignals(True)
        try:
            state = item.checkState(0)
            if state != Qt.PartiallyChecked:
                self._set_check_state(item, state)
            self._update_parent_states(item)
            self._rebuild_selected()
        finally:
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

    def _collect_from_item(self, item: QTreeWidgetItem, selected: set[str]) -> None:
        # is_dir is stored at scan time — no filesystem stat() calls here.
        is_dir = bool(item.data(0, ROLE_IS_DIR))
        rel_path = item.data(0, ROLE_REL_PATH)
        if not is_dir and rel_path and item.checkState(0) == Qt.Checked:
            selected.add(rel_path)
        for i in range(item.childCount()):
            self._collect_from_item(item.child(i), selected)

    def _select_all(self) -> None:
        self._set_all_checked(Qt.Checked)

    def _deselect_all(self) -> None:
        self._set_all_checked(Qt.Unchecked)

    def _set_all_checked(self, state: Qt.CheckState) -> None:
        root = self.tree.invisibleRootItem()
        if root.childCount() == 0:
            return
        self.tree.blockSignals(True)
        try:
            self._set_check_state(root.child(0), state)
            self._rebuild_selected()
        finally:
            self.tree.blockSignals(False)
        self._update_buttons()

    # ───────── Merging (background thread) ─────────

    def _merge_all(self) -> None:
        self._run_merger(spec=self.combined_spec, selected=set())

    def _merge_selected(self) -> None:
        selected = set(self.selected_paths)
        logger.info("Merge selected: %d files", len(selected))
        if not selected:
            QMessageBox.warning(self, "Нет файлов", "Не выбрано ни одного файла.")
            return
        self._run_merger(spec=self.combined_spec, selected=selected)

    def _run_merger(self, spec, selected: set[str]) -> None:
        if self.root_path is None:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку проекта.")
            return
        if self.merge_worker is not None and self.merge_worker.isRunning():
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

        self.statusBar().showMessage("Сборка проекта...")
        self._set_merge_buttons_enabled(False)
        self.merge_worker = MergerWorker(self.root_path, spec, selected, output, parent=self)
        self.merge_worker.merge_done.connect(self._on_merge_done)
        self.merge_worker.merge_failed.connect(self._on_merge_failed)
        self.merge_worker.merge_progress.connect(self._on_merge_progress)
        self.merge_worker.start()

    def _on_merge_progress(self, index: int, rel_path: str) -> None:
        self.statusBar().showMessage(f"Сборка: {rel_path}  ({index})")

    def _on_merge_done(self, file_count: int) -> None:
        self.merge_worker = None
        self._set_merge_buttons_enabled(True)
        self.statusBar().showMessage(f"Готово. Обработано файлов: {file_count}")
        QMessageBox.information(self, "Успех", f"Файл сохранён.\nФайлов обработано: {file_count}")

    def _on_merge_failed(self, message: str) -> None:
        self.merge_worker = None
        self._set_merge_buttons_enabled(True)
        self.statusBar().showMessage("Ошибка")
        QMessageBox.critical(self, "Ошибка", message)

    # ───────── Rules / .gitignore ─────────

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
            p for p in self.config.gitignore_patterns
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

        self.combined_spec = get_combined_spec(self.root_path, self.config.gitignore_patterns)
        self.statusBar().showMessage(".gitignore обновлён")
        QMessageBox.information(
            self, "Готово",
            f"Добавлены правила исключений в .gitignore ({len(new_patterns)} шт.)."
        )
        self._start_scan()

    def _edit_rules(self) -> None:
        dialog = RulesDialog(self.config.gitignore_patterns, self)
        if dialog.exec() != RulesDialog.Accepted:
            return
        self.config.set_gitignore_patterns(dialog.get_patterns())
        if self.root_path is not None:
            self.combined_spec = get_combined_spec(self.root_path, self.config.gitignore_patterns)
            self.statusBar().showMessage("Правила обновлены")
            self._start_scan()

    # ───────── Misc ─────────

    def _set_merge_buttons_enabled(self, enabled: bool) -> None:
        self.merge_all_btn.setEnabled(enabled)
        self.merge_selected_btn.setEnabled(enabled)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for btn in (
            self.select_all_btn,
            self.deselect_all_btn,
            self.merge_all_btn,
            self.merge_selected_btn,
            self.update_gitignore_btn,
            self.rules_btn,
        ):
            btn.setEnabled(enabled)

    def _update_buttons(self) -> None:
        self._set_controls_enabled(self.root_path is not None)

    def closeEvent(self, event) -> None:
        self._stop_scan_worker()
        if self.merge_worker is not None and self.merge_worker.isRunning():
            self.merge_worker.cancel()
            self.merge_worker.wait(5000)
        event.accept()
