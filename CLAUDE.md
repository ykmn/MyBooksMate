# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Update developing history in `docs/` folder as well as README.md on every change.

All `.py` source files live under `mybooksmate/` (including the entry point `mybooksmate/main.py`, the CLI core `mybooksmate/RUBookmatedownloader.py`, and the Windows bootstrap `mybooksmate/launcher.py`) — there is no top-level `.py` file in the project root anymore.

When editing any file under `mybooksmate/`, immediately copy the updated file(s) into **both** `release-Win/mybooksmate/` and `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/` (the Mac copy lives inside the app bundle's Resources folder, not at the `release-Mac/` top level) so both release builds stay in sync with the main project folder. Do this as part of the same change, not as a separate follow-up. Files that are platform-specific by nature (e.g. `requirements.txt`/`favicon.icns` only inside `release-Mac/MyBooksMate.app/Contents/Resources/`, `config.ini` only in `release-Win/` and `favicon.ico` only in `release-Win/`, `mybooksmate/launcher.py` only in `release-Win/mybooksmate/` since it's the Windows PyInstaller bootstrap entry and macOS uses its own bash bootstrap script) don't need mirroring both ways — only the cross-platform Python source does.

`mybooksmate/main.py`'s `_bundle_dir()` (icon lookup) and `config.py`'s `_app_dir()` (config.ini/token.txt/webengine_profile/download-folder default) are deliberately two different functions — don't merge them. `_app_dir()` honors the `MYBOOKSMATE_APP_DIR` env var override (set by the macOS bootstrap script to point at the user's writable data directory); `_bundle_dir()` never does, since icons are a static asset shipped with the app, not user data.

## Release folders

- `release-Win/` — Windows portable build: `MyBooksMate.exe` (a small PyInstaller-built bootstrap compiled from `mybooksmate/launcher.py`, icon `favicon.ico`) launches the app via the bundled `python-embed\pythonw.exe -m mybooksmate.main`, creating the embeddable Python's `pip`/dependencies on first run (no system Python required). Rebuild the exe after changing `mybooksmate/launcher.py`:
  ```
  python -m PyInstaller --onefile --noconsole --name "MyBooksMate" --icon "favicon.ico" --distpath ./release-Win --workpath ./build_tmp --specpath ./build_tmp mybooksmate/launcher.py
  ```
  then delete `build_tmp/` and `*.spec`.
- `release-Mac/` — macOS (Apple Silicon) build, **self-contained**: `release-Mac/` contains nothing but `MyBooksMate.app` — the whole folder is just staging, and the `.app` itself can be moved to `/Applications` (or anywhere) on its own, no sibling files required. `Contents/Info.plist`, `Contents/MacOS/MyBooksMate` (bash bootstrap script), `Contents/Resources/icon.icns` (Finder icon), `Contents/Resources/favicon.icns` (runtime window icon, found via `_bundle_dir()`), `Contents/Resources/requirements.txt`, `Contents/Resources/mybooksmate/` (the Python package). All *writable* data — `config.ini`, `token.txt`, `webengine_profile/`, and the first-run `.venv` itself — lives in `~/Library/Application Support/MyBooksMate` instead, so it survives app updates/reinstalls and the bundle never needs write access. The bootstrap script exports `MYBOOKSMATE_APP_DIR` pointing there (`mybooksmate/config.py`'s `_app_dir()` picks it up), creates the venv there on first run using the Mac's own `python3` (a prebuilt venv can't be shipped cross-platform from this Windows dev machine — PySide6/QtWebEngine wheels are platform-specific binaries), installs `Contents/Resources/requirements.txt`, then `cd`s into `Contents/Resources` and launches via `python3 -m mybooksmate.main` (subsequent launches reuse the venv via a marker file). This hasn't been tested on real macOS hardware — only verified for bash syntax and directory layout.
- Both icons are generated from `favicon.svg` via `QSvgRenderer` (PySide6) rendered to a 1024×1024 PNG, then `Pillow` saves multi-resolution `.ico` (Windows) and `.icns` (macOS) from that PNG. Regenerate both whenever the source SVG changes — remember to also re-copy `favicon.icns` into `release-Mac/MyBooksMate.app/Contents/Resources/`.
- `release-Calibre/` — a separate, self-contained Calibre store plugin ("Яндекс.Книги"), independent of the `mybooksmate/` package (no shared source, no sync rule with it). See `release-Calibre/README.md` for its own build/install instructions.

## Версионность

Все варианты приложения (`release-Win/`, `release-Mac/`, `release-Calibre/`) версионируются по схеме `major.minor.debug`, например `1.0.000`. Начальная версия — `1.0.000`.

- **debug** (третье число, 3 цифры) увеличивается на каждую доработку/фикс в любом из вариантов — это самая частая правка.
- **minor**/**major** меняются только по явному указанию пользователя (новая значимая функциональность / релиз).
- Источники версии:
  - Windows/macOS-приложение (общий код в `mybooksmate/`): `mybooksmate/version.py` (`__version__ = "1.0.000"`), отображается в заголовке окна (`main_window.py`) и `QApplication.setApplicationVersion` (`main.py`). Менять только в одном месте — `mybooksmate/version.py` — и копировать в `release-Win/mybooksmate/version.py` и `release-Mac/.../Resources/mybooksmate/version.py` по общему правилу синхронизации выше.
  - Calibre-плагин: `release-Calibre/__init__.py`, атрибут `version = (1, 0, 0)` (кортеж `(major, minor, debug)`, без ведущих нулей — `(1, 0, 0)` соответствует `"1.0.000"`).
- При любой правке кода в `mybooksmate/` или `release-Calibre/` увеличивай **debug**-версию соответствующего варианта в этом же изменении (не отдельным шагом).

## Project overview

**My Books Mate** — Windows/macOS-приложение для просмотра книг на https://books.yandex.ru и скачивания их локально.

