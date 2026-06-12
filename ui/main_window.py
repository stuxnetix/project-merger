"""Main application window."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import i18n
from config import Config
from gitignore_handler import create_default_gitignore, get_combined_spec, get_gitignore_spec
from i18n import tr
from merger import MergeResult
from scanner import FsNode
from ui.rules_dialog import RulesDialog
from ui.settings_dialog import SettingsDialog
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
        self._suppress_click = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon = QLabel("📂")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 56px;")

        plus = QLabel("+")
        plus.setAlignment(Qt.AlignCenter)
        plus.setStyleSheet("font-size: 40px; color: #64B5F6; font-weight: 300; margin-top: -8px;")

        self.text = QLabel(tr("drop_text"))
        self.text.setAlignment(Qt.AlignCenter)
        self.text.setStyleSheet("font-size: 15px; color: #546E7A; font-family: 'Segoe UI', system-ui, sans-serif;")

        layout.addWidget(icon)
        layout.addWidget(plus)
        layout.addWidget(self.text)

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
        if self._suppress_click:  # click landed on the recent-projects button
            self._suppress_click = False
            return
        dir_path = QFileDialog.getExistingDirectory(self, tr("choose_folder_dialog"))
        if dir_path:
            self.directory_selected.emit(dir_path)

    def retranslate(self) -> None:
        self.text.setText(tr("drop_text"))


class MainWindow(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.root_path: Path | None = None
        self.combined_spec = None
        self.selected_paths: set[str] = set()
        self.scan_worker: ScanWorker | None = None
        self.merge_worker: MergerWorker | None = None
        self.last_output_path: Path | None = None

        self.setWindowTitle(tr("app_title"))
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

        self.folder_label = QLabel(tr("no_project"))
        self.folder_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                font-family: 'Segoe UI', system-ui, sans-serif;
                color: #212121;
                padding: 4px 0;
            }
        """)

        self.change_folder_btn = QPushButton(tr("change_folder"))
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

        self.exit_btn = QPushButton(tr("exit_btn"))
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

        self.recent_btn = QPushButton(tr("recent_btn"))
        self.recent_btn.setStyleSheet(self.change_folder_btn.styleSheet())
        self.recent_menu = QMenu(self)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self.recent_btn.setMenu(self.recent_menu)

        self.settings_btn = QPushButton(tr("settings_btn"))
        self.settings_btn.setStyleSheet(self.change_folder_btn.styleSheet())
        self.settings_btn.clicked.connect(self._open_settings)

        top_layout.addWidget(self.folder_icon)
        top_layout.addWidget(self.folder_label)
        top_layout.addStretch()
        top_layout.addWidget(self.recent_btn)
        top_layout.addWidget(self.change_folder_btn)
        top_layout.addWidget(self.settings_btn)
        top_layout.addWidget(self.exit_btn)
        content_layout.addLayout(top_layout)

        self.tree_stack = QStackedWidget()

        loading_page = QWidget()
        loading_layout = QVBoxLayout(loading_page)
        loading_layout.setAlignment(Qt.AlignCenter)
        loading_layout.setSpacing(20)

        self.loading_label = QLabel(tr("loading_initial"))
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

        self.cancel_scan_btn = QPushButton(tr("cancel_scan"))
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
        self.tree.setHeaderLabels([tr("tree_header")])
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
        self.select_all_btn = QPushButton(tr("select_all"))
        self.select_all_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn = QPushButton(tr("deselect_all"))
        self.deselect_all_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.update_gitignore_btn = QPushButton(tr("update_gitignore"))
        self.update_gitignore_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        self.update_gitignore_btn.clicked.connect(self._update_gitignore)
        self.rules_btn = QPushButton(tr("rules_btn"))
        self.rules_btn.setStyleSheet(SECONDARY_BTN_STYLE)
        self.rules_btn.clicked.connect(self._edit_rules)
        self.sanitize_checkbox = QCheckBox(tr("sanitize_checkbox"))
        self.sanitize_checkbox.setToolTip(tr("sanitize_tooltip"))
        self.sanitize_checkbox.setStyleSheet(
            "QCheckBox { font-size: 13px; font-family: 'Segoe UI', system-ui, sans-serif; color: #212121; }"
        )
        self.sanitize_checkbox.setChecked(self.config.sanitize_secrets)
        self.sanitize_checkbox.toggled.connect(self._on_sanitize_toggled)
        self.merge_all_btn = QPushButton(tr("merge_all"))
        self.merge_all_btn.setStyleSheet(BTN_STYLE)
        self.merge_all_btn.clicked.connect(self._merge_all)
        self.merge_selected_btn = QPushButton(tr("merge_selected"))
        self.merge_selected_btn.setStyleSheet(BTN_STYLE)
        self.merge_selected_btn.clicked.connect(self._merge_selected)

        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addWidget(self.update_gitignore_btn)
        btn_layout.addWidget(self.rules_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.sanitize_checkbox)
        btn_layout.addWidget(self.merge_all_btn)
        btn_layout.addWidget(self.merge_selected_btn)
        content_layout.addLayout(btn_layout)

        self.stack.addWidget(content)
        main_layout.addWidget(self.stack)

        self.statusBar().showMessage(tr("status_ready"))
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
        t0 = time.perf_counter()
        self._stop_scan_worker()

        self.root_path = Path(dir_path)
        self.config.last_source_dir = str(self.root_path)  # deferred save — no disk write here
        self.config.add_recent_project(str(self.root_path))
        self.folder_label.setText(str(self.root_path))
        t1 = time.perf_counter()

        spec = get_gitignore_spec(self.root_path)
        t2 = time.perf_counter()
        logger.info(
            "perf: pre-scan prepare %.0f ms, .gitignore check %.0f ms",
            (t1 - t0) * 1000, (t2 - t1) * 1000,
        )
        if spec is None:
            reply = QMessageBox.question(
                self,
                tr("gitignore_missing_title"),
                tr("gitignore_missing_text"),
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
            self, tr("choose_folder_dialog"), self.config.last_source_dir
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
        self.loading_label.setText(tr("loading_initial"))
        self.statusBar().showMessage(tr("status_scanning_files"))
        self._set_controls_enabled(False)

        self.scan_worker = ScanWorker(self.root_path, self.combined_spec, parent=self)
        self.scan_worker.scan_done.connect(self._on_scan_done)
        self.scan_worker.scan_failed.connect(self._on_scan_failed)
        self.scan_worker.scan_progress.connect(self._on_scan_progress)
        self.scan_worker.start()

    def _stop_scan_worker(self) -> None:
        if self.scan_worker is not None:
            worker, self.scan_worker = self.scan_worker, None
            self._shutdown_worker(worker, "scan")

    @staticmethod
    def _shutdown_worker(worker, name: str) -> None:
        """Stop a worker thread, escalating to terminate() as a last resort.

        A QThread still alive at window destruction keeps the Python process
        running — on Windows that leaves a zombie console window that the user
        cannot close normally.
        """
        worker.cancel()
        if not worker.wait(3000):
            logger.warning("%s worker did not stop in time — terminating", name)
            worker.terminate()
            worker.wait(1000)

    def _cancel_scan(self) -> None:
        logger.info("Scan cancelled by user")
        self._stop_scan_worker()
        self.statusBar().showMessage(tr("status_scan_cancelled"))
        self.stack.setCurrentIndex(PAGE_DROP)

    def _on_scan_progress(self, count: int, rel_path: str) -> None:
        self.loading_label.setText(tr("loading_progress", count=count))
        self.statusBar().showMessage(tr("status_scanning", path=rel_path, count=count))

    def _on_scan_failed(self, message: str) -> None:
        self._release_scan_worker()
        self._set_controls_enabled(True)
        self.statusBar().showMessage(tr("status_scan_error"))
        self.stack.setCurrentIndex(PAGE_DROP)
        QMessageBox.critical(self, tr("scan_error_title"), message)

    def _release_scan_worker(self) -> None:
        """Drop the worker reference only after the thread fully exited.

        The done/failed signals are delivered while ``run()`` may still be
        returning; waiting here guarantees no QThread is alive when the window
        is later destroyed.
        """
        if self.scan_worker is not None:
            self.scan_worker.wait(2000)
            self.scan_worker = None

    def _on_scan_done(self, fs_root: FsNode, count: int) -> None:
        self._release_scan_worker()
        self._populate_tree(fs_root)
        self.tree_stack.setCurrentIndex(TREE_PAGE_TREE)
        self._set_controls_enabled(True)
        self.statusBar().showMessage(tr("status_loaded", path=self.root_path, count=count))

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
            QMessageBox.warning(self, tr("no_files_title"), tr("no_files_text"))
            return
        self._run_merger(spec=self.combined_spec, selected=selected)

    def _run_merger(self, spec, selected: set[str]) -> None:
        if self.root_path is None:
            QMessageBox.warning(self, tr("err_title"), tr("no_project_first"))
            return
        if self.merge_worker is not None and self.merge_worker.isRunning():
            QMessageBox.warning(self, tr("busy_title"), tr("busy_text"))
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("save_dialog_title"),
            str(Path(self.config.last_output_dir) / "project_merged.md"),
            tr("save_dialog_filter"),
        )
        if not save_path:
            return
        output = Path(save_path)
        self.config.last_output_dir = str(output.parent)
        self.last_output_path = output

        self.statusBar().showMessage(tr("status_merge_running"))
        self._set_merge_buttons_enabled(False)
        self.merge_worker = MergerWorker(
            self.root_path,
            spec,
            selected,
            output,
            sanitize=self.sanitize_checkbox.isChecked(),
            max_file_size_kb=self.config.max_file_size_kb,
            parent=self,
        )
        self.merge_worker.merge_done.connect(self._on_merge_done)
        self.merge_worker.merge_failed.connect(self._on_merge_failed)
        self.merge_worker.merge_progress.connect(self._on_merge_progress)
        self.merge_worker.start()

    def _on_merge_progress(self, index: int, rel_path: str) -> None:
        self.statusBar().showMessage(tr("status_merging", path=rel_path, index=index))

    def _release_merge_worker(self) -> None:
        if self.merge_worker is not None:
            self.merge_worker.wait(2000)
            self.merge_worker = None

    def _on_merge_done(self, result: MergeResult) -> None:
        self._release_merge_worker()
        self._set_merge_buttons_enabled(True)
        self.statusBar().showMessage(tr("status_done", count=result.files_written))
        self._show_merge_report(result)

    def _show_merge_report(self, result: MergeResult) -> None:
        lines = [tr("success_text", count=result.files_written)]
        if result.total_chars:
            lines.append(tr("success_tokens", tokens=f"{result.token_estimate:,}".replace(",", " ")))
        if result.sanitized:
            if result.findings_count:
                lines.append("")
                lines.append(tr("sanitize_summary", n=result.findings_count, m=len(result.findings)))
                lines.append(tr("sanitize_disclaimer"))
            else:
                lines.append("")
                lines.append(tr("sanitize_none"))

        box = QMessageBox(QMessageBox.Information, tr("success_title"), "\n".join(lines), parent=self)
        if result.findings:
            details: list[str] = []
            for rel_path, findings in result.findings.items():
                details.append(rel_path)
                for f in findings:
                    details.append(f"    {f.rule} — line {f.line}")
            box.setDetailedText("\n".join(details))
        copy_button = box.addButton(tr("copy_btn"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.setDefaultButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is copy_button:
            self._copy_output_to_clipboard()

    def _copy_output_to_clipboard(self) -> None:
        if self.last_output_path is None:
            return
        try:
            text = self.last_output_path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, tr("err_title"), str(e))
            return
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage(tr("status_copied"))

    def _on_merge_failed(self, message: str) -> None:
        self._release_merge_worker()
        self._set_merge_buttons_enabled(True)
        self.statusBar().showMessage(tr("status_error"))
        QMessageBox.critical(self, tr("err_title"), message)

    # ───────── Rules / .gitignore ─────────

    def _update_gitignore(self) -> None:
        if self.root_path is None:
            QMessageBox.warning(self, tr("err_title"), tr("no_project_first"))
            return

        gitignore_path = self.root_path / ".gitignore"
        if not gitignore_path.is_file():
            QMessageBox.warning(self, tr("file_not_found_title"), tr("gitignore_absent_text"))
            return

        existing_patterns: set[str] = set()
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        existing_patterns.add(stripped)
        except OSError as e:
            QMessageBox.critical(self, tr("err_title"), tr("gitignore_read_error", error=e))
            return

        new_patterns = [
            p for p in self.config.gitignore_patterns
            if p not in existing_patterns
        ]
        if not new_patterns:
            QMessageBox.information(self, tr("done_title"), tr("gitignore_all_present"))
            return

        try:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\n# Добавлено Project Merger\n")
                for pattern in new_patterns:
                    f.write(f"{pattern}\n")
        except OSError as e:
            QMessageBox.critical(self, tr("err_title"), tr("gitignore_write_error", error=e))
            return

        self.combined_spec = get_combined_spec(self.root_path, self.config.gitignore_patterns)
        self.statusBar().showMessage(tr("status_gitignore_updated"))
        QMessageBox.information(
            self, tr("done_title"),
            tr("gitignore_added", count=len(new_patterns)),
        )
        self._start_scan()

    def _edit_rules(self) -> None:
        dialog = RulesDialog(self.config.gitignore_patterns, self)
        if dialog.exec() != RulesDialog.Accepted:
            return
        self.config.set_gitignore_patterns(dialog.get_patterns())
        if self.root_path is not None:
            self.combined_spec = get_combined_spec(self.root_path, self.config.gitignore_patterns)
            self.statusBar().showMessage(tr("status_rules_updated"))
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

    # ───────── v3 options ─────────

    def _on_sanitize_toggled(self, checked: bool) -> None:
        self.config.sanitize_secrets = checked  # deferred save

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.config.recent_projects
        if not recent:
            action = self.recent_menu.addAction(tr("recent_empty"))
            action.setEnabled(False)
            return
        for path in recent:
            action = self.recent_menu.addAction(path)
            action.triggered.connect(lambda checked=False, p=path: self._open_recent(p))

    def _open_recent(self, path: str) -> None:
        if not Path(path).is_dir():
            self.config.remove_recent_project(path)
            QMessageBox.warning(self, tr("recent_missing_title"), tr("recent_missing_text", path=path))
            return
        self._load_project(path)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config.language, self.config.max_file_size_kb, self)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        self.config.max_file_size_kb = dialog.get_max_file_size_kb()
        new_lang = dialog.get_language()
        if new_lang != self.config.language:
            self.config.language = new_lang
            i18n.set_language(new_lang)
            self._retranslate()
        self.config.flush()

    def _retranslate(self) -> None:
        """Re-apply all static UI texts after a language switch."""
        self.setWindowTitle(tr("app_title"))
        self.drop_zone.retranslate()
        if self.root_path is None:
            self.folder_label.setText(tr("no_project"))
        self.recent_btn.setText(tr("recent_btn"))
        self.change_folder_btn.setText(tr("change_folder"))
        self.settings_btn.setText(tr("settings_btn"))
        self.exit_btn.setText(tr("exit_btn"))
        self.loading_label.setText(tr("loading_initial"))
        self.cancel_scan_btn.setText(tr("cancel_scan"))
        self.tree.setHeaderLabels([tr("tree_header")])
        self.select_all_btn.setText(tr("select_all"))
        self.deselect_all_btn.setText(tr("deselect_all"))
        self.update_gitignore_btn.setText(tr("update_gitignore"))
        self.rules_btn.setText(tr("rules_btn"))
        self.sanitize_checkbox.setText(tr("sanitize_checkbox"))
        self.sanitize_checkbox.setToolTip(tr("sanitize_tooltip"))
        self.merge_all_btn.setText(tr("merge_all"))
        self.merge_selected_btn.setText(tr("merge_selected"))
        self.statusBar().showMessage(tr("status_ready"))

    def closeEvent(self, event) -> None:
        self._stop_scan_worker()
        if self.merge_worker is not None:
            worker, self.merge_worker = self.merge_worker, None
            self._shutdown_worker(worker, "merge")
        self.config.flush()  # persist deferred changes (last dirs)
        event.accept()
