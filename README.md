# Project Merger

Графическое приложение на Python (PySide6) для объединения файлов проекта в единый Markdown-документ с сохранением структуры и поддержкой `.gitignore`.

## Возможности

- Выбор корневой папки проекта через GUI
- Автоматическое обнаружение и парсинг `.gitignore` (библиотека `pathspec`)
- Создание `.gitignore` с типовыми шаблонами при его отсутствии
- Древовидный просмотр файлов с чекбоксами для ручного выбора
- Фильтрация двоичных файлов (с запасным определением кодировки через `chardet`)
- Генерация Markdown-файла с подсветкой синтаксиса по расширению
- Фоновый поток (QThread) — интерфейс не зависает
- Сохранение последних директорий и настроек в `~/.project_merger_config.json`
- Логирование в консоль и файл `project_merger.log`

## Структура проекта

```
project_merger/
├── main.py                  # Точка входа: настройка логирования и запуск приложения
├── config.py                # Сохранение и загрузка пользовательских настроек (JSON)
├── gitignore_handler.py     # Поиск, создание и парсинг .gitignore через pathspec
├── merger.py                # Сканирование, фильтрация файлов и генерация Markdown
├── requirements.txt         # Зависимости: PySide6, pathspec, chardet
├── install.bat              # Установщик для Windows
├── install.sh               # Установщик для Linux
├── ui/                      # Пакет графического интерфейса
│   ├── __init__.py
│   ├── main_window.py       # Главное окно: дерево файлов, чекбоксы, кнопки сборки
│   └── workers.py           # Фоновый поток (QThread) для генерации Markdown
└── README.md                # Этот файл
```

## Установка

### Windows

Запустите `install.bat` двойным щелчком или в терминале:

```cmd
install.bat
```

### Linux

```bash
chmod +x install.sh
./install.sh
```

### Ручная установка

```bash
pip install -r requirements.txt
```

## Запуск

```bash
python main.py        # Windows
python3 main.py       # Linux
```

## Зависимости

- **Python ≥ 3.10**
- **PySide6 ≥ 6.5** — графический интерфейс
- **pathspec ≥ 0.11** — парсинг `.gitignore`
- **chardet ≥ 5.0** — определение кодировки (опционально)
