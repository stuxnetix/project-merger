"""Lightweight UI translation layer (Russian / English).

Pure Python, no Qt dependency — usable from worker threads and core modules.
Strings are looked up by key via :func:`tr`; the active language is set once at
startup from the config and can be switched at runtime (the main window then
calls its ``_retranslate()``).

For more than two languages the standard Qt Linguist pipeline (.ts/.qm +
QTranslator) would be the next step; for RU/EN a transparent dict keeps the
project dependency-free and trivially testable.
"""
from __future__ import annotations

LANGUAGES = ("ru", "en")

_current = "ru"


def set_language(lang: str) -> None:
    global _current
    _current = lang if lang in LANGUAGES else "ru"


def get_language() -> str:
    return _current


def tr(key: str, **kwargs: object) -> str:
    """Return the translated string for *key*, formatted with *kwargs*."""
    entry = STRINGS.get(key)
    if entry is None:  # missing key — fail loudly in logs, softly in UI
        return key
    text = entry.get(_current) or entry["ru"]
    return text.format(**kwargs) if kwargs else text


STRINGS: dict[str, dict[str, str]] = {
    # ───────── main window ─────────
    "app_title": {"ru": "Project Merger", "en": "Project Merger"},
    "drop_text": {
        "ru": "Перетащите проект сюда\nили нажмите чтобы открыть",
        "en": "Drag a project folder here\nor click to open",
    },
    "choose_folder_dialog": {"ru": "Выберите корневую папку проекта", "en": "Select the project root folder"},
    "no_project": {"ru": "Проект не выбран", "en": "No project selected"},
    "change_folder": {"ru": "Открыть другой проект", "en": "Open another project"},
    "recent_btn": {"ru": "Недавние проекты ▾", "en": "Recent projects ▾"},
    "recent_empty": {"ru": "(список пуст)", "en": "(empty)"},
    "recent_missing_title": {"ru": "Папка не найдена", "en": "Folder not found"},
    "recent_missing_text": {
        "ru": "Папка больше не существует:\n{path}\n\nЗапись удалена из списка.",
        "en": "The folder no longer exists:\n{path}\n\nThe entry was removed from the list.",
    },
    "settings_btn": {"ru": "⚙ Настройки", "en": "⚙ Settings"},
    "exit_btn": {"ru": "✕ Выход", "en": "✕ Exit"},
    "loading_initial": {"ru": "⏳  Сканирование файловой системы...", "en": "⏳  Scanning file system..."},
    "loading_progress": {"ru": "⏳  Сканирование: {count} элементов...", "en": "⏳  Scanning: {count} items..."},
    "cancel_scan": {"ru": "✕ Отменить сканирование", "en": "✕ Cancel scan"},
    "tree_header": {"ru": "Файлы и папки", "en": "Files and folders"},
    "select_all": {"ru": "✓ Выделить всё", "en": "✓ Select all"},
    "deselect_all": {"ru": "✕ Снять всё", "en": "✕ Deselect all"},
    "update_gitignore": {"ru": "Обновить .gitignore", "en": "Update .gitignore"},
    "rules_btn": {"ru": "Правила", "en": "Rules"},
    "merge_all": {"ru": "Собрать весь проект", "en": "Merge entire project"},
    "merge_selected": {"ru": "Собрать выбранное", "en": "Merge selected"},
    "sanitize_checkbox": {"ru": "Очистить секреты", "en": "Sanitize secrets"},
    "sanitize_tooltip": {
        "ru": "Маскирует в итоговом документе токены, пароли, email и другие секреты\n"
              "(***REDACTED***). Внимание: автоматическая проверка не даёт 100% гарантии —\n"
              "просмотрите результат перед публикацией.",
        "en": "Masks tokens, passwords, emails and other secrets in the output document\n"
              "(***REDACTED***). Note: automated detection is not a 100% guarantee —\n"
              "review the result before publishing.",
    },
    # ───────── status bar ─────────
    "status_ready": {"ru": "Готов", "en": "Ready"},
    "status_scanning_files": {"ru": "Сканирование файлов...", "en": "Scanning files..."},
    "status_scanning": {"ru": "Сканирование: {path}  ({count})", "en": "Scanning: {path}  ({count})"},
    "status_scan_cancelled": {"ru": "Сканирование отменено", "en": "Scan cancelled"},
    "status_scan_error": {"ru": "Ошибка сканирования", "en": "Scan error"},
    "status_loaded": {"ru": "Загружен проект: {path}  ({count} элементов)", "en": "Project loaded: {path}  ({count} items)"},
    "status_merging": {"ru": "Сборка: {path}  ({index})", "en": "Merging: {path}  ({index})"},
    "status_merge_running": {"ru": "Сборка проекта...", "en": "Merging project..."},
    "status_done": {"ru": "Готово. Обработано файлов: {count}", "en": "Done. Files processed: {count}"},
    "status_error": {"ru": "Ошибка", "en": "Error"},
    "status_copied": {"ru": "Документ скопирован в буфер обмена", "en": "Document copied to clipboard"},
    "status_rules_updated": {"ru": "Правила обновлены", "en": "Rules updated"},
    "status_gitignore_updated": {"ru": ".gitignore обновлён", "en": ".gitignore updated"},
    # ───────── dialogs ─────────
    "err_title": {"ru": "Ошибка", "en": "Error"},
    "scan_error_title": {"ru": "Ошибка сканирования", "en": "Scan error"},
    "gitignore_missing_title": {"ru": ".gitignore не найден", "en": ".gitignore not found"},
    "gitignore_missing_text": {
        "ru": "Файл .gitignore отсутствует. Создать его с типовыми исключениями?",
        "en": "No .gitignore file found. Create one with standard exclusions?",
    },
    "no_files_title": {"ru": "Нет файлов", "en": "No files"},
    "no_files_text": {"ru": "Не выбрано ни одного файла.", "en": "No files selected."},
    "no_project_first": {"ru": "Сначала выберите папку проекта.", "en": "Select a project folder first."},
    "busy_title": {"ru": "Занято", "en": "Busy"},
    "busy_text": {"ru": "Генерация уже выполняется. Дождитесь завершения.", "en": "A merge is already running. Please wait for it to finish."},
    "save_dialog_title": {"ru": "Сохранить project_merged.md", "en": "Save project_merged.md"},
    "save_dialog_filter": {"ru": "Markdown (*.md)", "en": "Markdown (*.md)"},
    "success_title": {"ru": "Успех", "en": "Success"},
    "success_text": {"ru": "Файл сохранён.\nФайлов обработано: {count}", "en": "File saved.\nFiles processed: {count}"},
    "success_tokens": {"ru": "Объём: ≈ {tokens} токенов (оценка для LLM)", "en": "Size: ≈ {tokens} tokens (LLM estimate)"},
    "copy_btn": {"ru": "Копировать в буфер", "en": "Copy to clipboard"},
    "sanitize_none": {"ru": "Секреты: не обнаружены.", "en": "Secrets: none found."},
    "sanitize_summary": {
        "ru": "Замаскировано секретов: {n} (в файлах: {m}). Подробности — в «Show Details».",
        "en": "Secrets masked: {n} (in {m} files). See “Show Details”.",
    },
    "sanitize_disclaimer": {
        "ru": "Автоматическая очистка не даёт 100% гарантии — просмотрите документ перед публикацией.",
        "en": "Automated sanitizing is not a 100% guarantee — review the document before publishing.",
    },
    "file_not_found_title": {"ru": "Файл не найден", "en": "File not found"},
    "gitignore_absent_text": {"ru": ".gitignore отсутствует в корне проекта.", "en": "No .gitignore in the project root."},
    "gitignore_read_error": {"ru": "Не удалось прочитать .gitignore:\n{error}", "en": "Could not read .gitignore:\n{error}"},
    "gitignore_write_error": {"ru": "Не удалось записать .gitignore:\n{error}", "en": "Could not write .gitignore:\n{error}"},
    "done_title": {"ru": "Готово", "en": "Done"},
    "gitignore_all_present": {
        "ru": "Все правила из шаблона уже присутствуют в .gitignore.",
        "en": "All template rules are already present in .gitignore.",
    },
    "gitignore_added": {
        "ru": "Добавлены правила исключений в .gitignore ({count} шт.).",
        "en": "Exclusion rules added to .gitignore ({count}).",
    },
    # ───────── rules dialog ─────────
    "rules_title": {"ru": "Правила исключений", "en": "Exclusion rules"},
    "rules_hint": {"ru": "Шаблон правил для исключения файлов и папок:", "en": "Rule template for excluding files and folders:"},
    "rules_placeholder": {"ru": "Новое правило (например, *.log или temp/)", "en": "New rule (e.g. *.log or temp/)"},
    "rules_add": {"ru": "Добавить", "en": "Add"},
    "rules_remove": {"ru": "Удалить выбранное", "en": "Remove selected"},
    "rules_reset": {"ru": "Сбросить к стандартным", "en": "Reset to defaults"},
    "rules_reset_title": {"ru": "Сбросить правила", "en": "Reset rules"},
    "rules_reset_text": {"ru": "Заменить текущий список стандартным набором правил?", "en": "Replace the current list with the default rule set?"},
    "ok": {"ru": "OK", "en": "OK"},
    "cancel": {"ru": "Отмена", "en": "Cancel"},
    # ───────── settings dialog ─────────
    "settings_title": {"ru": "Настройки", "en": "Settings"},
    "settings_language": {"ru": "Язык интерфейса:", "en": "Interface language:"},
    "settings_lang_ru": {"ru": "Русский", "en": "Русский (Russian)"},
    "settings_lang_en": {"ru": "English (английский)", "en": "English"},
    "settings_size_limit": {"ru": "Лимит размера файла, КБ (0 — без лимита):", "en": "File size limit, KB (0 — no limit):"},
    "settings_size_hint": {
        "ru": "Файлы больше лимита не включаются в документ целиком —\nвместо содержимого вставляется пометка о пропуске.",
        "en": "Files larger than the limit are not embedded in the document —\na skip note is inserted instead of the content.",
    },
    # ───────── document indicators (written into the output .md) ─────────
    "doc_binary": {"ru": "[двоичный файл]", "en": "[binary file]"},
    "doc_empty": {"ru": "[пустой файл]", "en": "[empty file]"},
    "doc_read_error": {"ru": "*Ошибка чтения файла*", "en": "*File read error*"},
    "doc_tree_header": {"ru": "Структура проекта", "en": "Project structure"},
    "doc_skipped_size": {
        "ru": "[файл пропущен: {size} КБ превышает лимит {limit} КБ]",
        "en": "[file skipped: {size} KB exceeds the {limit} KB limit]",
    },
    "doc_sanitize_note": {
        "ru": "*Документ обработан очисткой секретов: замаскировано {n} значений.*",
        "en": "*Secret sanitizing applied: {n} values masked.*",
    },
}
