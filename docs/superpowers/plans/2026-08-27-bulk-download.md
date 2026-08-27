# Bulk Book Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user select and download multiple books at once from the Author/books, Series, and Section pages on books.yandex.ru, via a new "Выбрать книги..." button, a lazy-scroll page scraper, and a checkable selection dialog.

**Architecture:** Three new/changed pieces, each with one responsibility:
- `mybooksmate/page_scraper.py` (new) — lazy-scrolls the embedded browser and extracts book links via injected JS, with no dependency on the site's CSS/markup (URL-pattern based, like the rest of the codebase).
- `mybooksmate/book_selection_dialog.py` (new) — a modal `QDialog` that owns a `PageScraper`, shows collection progress, and lets the user check which books to download.
- `mybooksmate/main_window.py` (modified) — shows/hides the new button based on the current URL, and sequentially downloads the checked items by reusing the existing `worker.start_download`/`downloader.find_existing_file` machinery unchanged.

**Tech Stack:** PySide6 (`QWebEngineView.page().runJavaScript`, `QTimer`, `QDialog`, `QListWidget`), plain injected JavaScript (no site-specific selectors — URL-pattern matching only).

## Global Constraints

- All `.py` source lives under `mybooksmate/`; no top-level `.py` files (per `CLAUDE.md`).
- After editing/creating any file under `mybooksmate/`, immediately copy it into **both** `release-Win/mybooksmate/` and `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/` in the same change (per `CLAUDE.md`).
- Bump the debug component of `mybooksmate/version.py`'s `__version__` (currently `"1.0.004"` — verify the current value before bumping, it may have moved) in the same change as any `mybooksmate/` edit, and copy `version.py` to both release folders too (per `CLAUDE.md` "Версионность").
- Update `docs/CHANGELOG.md` and `README.md` to reflect the change (per `CLAUDE.md`).
- No automated test suite exists for this project (confirmed: no `pytest` in `requirements.txt` or the shared `.venv`). Do not introduce a test framework or a `tests/` directory — verification is via standalone Python scripts run directly (`python -c "..."` or a throwaway `.py` file deleted after use), matching how prior work in this codebase was verified (e.g. `ast.parse` sanity checks).
- The shared virtual environment with PySide6 installed lives at `D:\Projects\MyBooksMate\.venv` (NOT inside this task's worktree, which is git-ignored and worktree-local). Run verification scripts with `D:\Projects\MyBooksMate\.venv\Scripts\python.exe`, invoked from inside the worktree directory so `import mybooksmate...` resolves against the worktree's (modified) source, not the main checkout's.
- Design doc: `docs/superpowers/specs/2026-08-27-bulk-download-design.md`.
- **Hard-won lesson from the previous plan on this repo:** a Qt/PySide6 API that looks right (`QWebEnginePage.createStandardContextMenu()`) turned out not to exist at all, and this was only caught when a human manually launched the app — no per-task or final review caught it from reading the diff alone. Every task in this plan that touches real `QWebEngineView`/`QWebEnginePage` behavior (Task 3 especially) must be manually launched and clicked through by a human (via the `run` skill's guidance) before the branch is considered done — do not let this slide to "final review will catch it."

---

### Task 1: `page_scraper.py` — lazy-scroll JS collector

**Files:**
- Create: `mybooksmate/page_scraper.py`
- Modify: `mybooksmate/version.py` (bump debug version)
- Mirror (create): `release-Win/mybooksmate/page_scraper.py`, `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/page_scraper.py`
- Mirror (modify): `release-Win/mybooksmate/version.py`, `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py`

**Interfaces:**
- Consumes: nothing from other tasks (this is the lowest-level new module).
- Produces (consumed by Task 2): `PageScraper` class with:
  - `PageScraper(browser)` — `browser` is any object exposing `.page()` which returns an object exposing `.runJavaScript(script: str, callback=None)` (a real `QWebEngineView`, or a duck-typed stub for testing).
  - `collect(self, on_done, on_progress=None)` — starts collection; `on_done` is called exactly once with `items: list[dict]` (`{"resource_type": str, "uuid": str, "title": str}`) when the page's book-link count has stabilized or the timeout elapsed. `on_progress`, if given, is called on every tick with the current `count: int`.
  - `stop(self)` — cancels collection; guarantees `on_done`/`on_progress` will never fire again after this call.

- [ ] **Step 1: Write `mybooksmate/page_scraper.py`**

```python
import time

from PySide6.QtCore import QTimer

# Same segment->resource_type mapping as main_window.py's URL_SEGMENT_TO_RESOURCE,
# duplicated here in JS form since this string is injected into the page, not
# imported from Python.
COLLECT_BOOKS_JS = """
(function() {
    var segmentToType = {
        books: "book",
        audiobooks: "audiobook",
        comicbooks: "comicbook",
        serial: "serial",
        series: "series"
    };
    var pattern = /\\/(books|audiobooks|comicbooks|serial|series)\\/([^\\/?#]+)/;
    var seen = {};
    var items = [];
    var anchors = document.querySelectorAll("a[href]");
    for (var i = 0; i < anchors.length; i++) {
        var anchor = anchors[i];
        var match = pattern.exec(anchor.getAttribute("href") || "");
        if (!match) { continue; }
        var resourceType = segmentToType[match[1]];
        var uuid = match[2];
        var key = resourceType + ":" + uuid;
        if (seen[key]) { continue; }
        seen[key] = true;
        var title = (anchor.textContent || "").trim();
        if (!title) {
            title = (anchor.getAttribute("aria-label") || anchor.getAttribute("title") || "").trim();
        }
        if (!title) {
            title = uuid;
        }
        items.push({resource_type: resourceType, uuid: uuid, title: title});
    }
    return {items: items, count: items.length, scrollHeight: document.body.scrollHeight};
})();
"""

TICK_INTERVAL_MS = 500
SETTLE_DELAY_MS = 150
STABLE_TICKS_REQUIRED = 3
MAX_COLLECT_SECONDS = 30


def _is_stable(history):
    """history: list of (count, scroll_height) tuples, oldest first. Returns
    True once the most recent STABLE_TICKS_REQUIRED entries are all identical
    (the lazy-loaded list has stopped growing)."""
    if len(history) < STABLE_TICKS_REQUIRED:
        return False
    return len(set(history[-STABLE_TICKS_REQUIRED:])) == 1


class PageScraper:
    """Lazy-scrolls `browser` to the bottom repeatedly, re-extracting book
    links after each scroll via COLLECT_BOOKS_JS, until the link count and
    document height stop changing (or a timeout elapses). Extraction is
    purely URL-pattern based — no dependency on the site's CSS classes or
    markup, matching main_window.py's own URL_PATTERN/URL_SEGMENT_TO_RESOURCE
    approach."""

    def __init__(self, browser):
        self._browser = browser
        self._history = []
        self._start_time = None
        self._on_done = None
        self._on_progress = None
        self._timer = QTimer()
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def collect(self, on_done, on_progress=None):
        self._on_done = on_done
        self._on_progress = on_progress
        self._history = []
        self._start_time = time.monotonic()
        self._timer.start()
        self._tick()

    def stop(self):
        self._timer.stop()
        self._on_done = None
        self._on_progress = None

    def _tick(self):
        if self._on_done is None:
            return
        self._browser.page().runJavaScript("window.scrollTo(0, document.body.scrollHeight);")
        QTimer.singleShot(SETTLE_DELAY_MS, self._collect_once)

    def _collect_once(self):
        if self._on_done is None:
            return
        self._browser.page().runJavaScript(COLLECT_BOOKS_JS, self._on_collected)

    def _on_collected(self, result):
        if self._on_done is None:
            return
        result = result or {}
        items = result.get("items", [])
        count = result.get("count", 0)
        scroll_height = result.get("scrollHeight", 0)
        self._history.append((count, scroll_height))

        if self._on_progress is not None:
            self._on_progress(count)

        timed_out = (time.monotonic() - self._start_time) >= MAX_COLLECT_SECONDS
        if _is_stable(self._history) or timed_out:
            self._timer.stop()
            on_done = self._on_done
            self._on_done = None
            self._on_progress = None
            on_done(items)
```

- [ ] **Step 2: Verify `_is_stable` with a standalone script (no Qt needed for this specific function)**

From the worktree root, run:

```bash
D:\Projects\MyBooksMate\.venv\Scripts\python.exe -c "
from mybooksmate.page_scraper import _is_stable

assert _is_stable([]) is False
assert _is_stable([(1, 100)]) is False
assert _is_stable([(1, 100), (1, 100)]) is False
assert _is_stable([(1, 100), (1, 100), (1, 100)]) is True
assert _is_stable([(1, 100), (2, 150), (2, 150)]) is False
assert _is_stable([(1, 100), (2, 150), (2, 150), (2, 150)]) is True
assert _is_stable([(2, 150), (2, 150), (2, 150), (3, 200)]) is False
print('all _is_stable checks passed')
"
```

Expected output: `all _is_stable checks passed`. If it fails with an `ImportError` about PySide6, confirm you're running the `.venv`'s python, not a bare `python`.

- [ ] **Step 3: Verify the module imports cleanly and `PageScraper` wires up against a stub browser**

```bash
D:\Projects\MyBooksMate\.venv\Scripts\python.exe -c "
from mybooksmate.page_scraper import PageScraper

class StubPage:
    def runJavaScript(self, script, callback=None):
        pass  # no-op: we only check construction/collect/stop don't raise

class StubBrowser:
    def page(self):
        return StubPage()

scraper = PageScraper(StubBrowser())
scraper.collect(on_done=lambda items: None, on_progress=lambda count: None)
scraper.stop()
print('PageScraper construction/collect/stop did not raise')
"
```

Expected output: `PageScraper construction/collect/stop did not raise`.

Note: this does NOT exercise the real timer ticks or JS round-trip (that requires a live `QWebEngineView` on a real page, which happens end-to-end in Task 3/4). It only proves the module is syntactically and structurally correct.

- [ ] **Step 4: Bump the debug version**

Read the current value in `mybooksmate/version.py` and increment the debug (third) component by 1.

- [ ] **Step 5: Mirror the new file and version.py into both release folders**

```bash
cp mybooksmate/page_scraper.py release-Win/mybooksmate/page_scraper.py
cp mybooksmate/page_scraper.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/page_scraper.py"
cp mybooksmate/version.py release-Win/mybooksmate/version.py
cp mybooksmate/version.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
```

- [ ] **Step 6: Commit**

```bash
git add mybooksmate/page_scraper.py mybooksmate/version.py \
  release-Win/mybooksmate/page_scraper.py release-Win/mybooksmate/version.py \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/page_scraper.py" \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
git commit -m "$(cat <<'EOF'
Add PageScraper: lazy-scroll book link collector for bulk download

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `book_selection_dialog.py` — checkable selection dialog

**Files:**
- Create: `mybooksmate/book_selection_dialog.py`
- Modify: `mybooksmate/version.py` (bump debug version again)
- Mirror (create): `release-Win/mybooksmate/book_selection_dialog.py`, `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/book_selection_dialog.py`
- Mirror (modify): `release-Win/mybooksmate/version.py`, `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py`

**Interfaces:**
- Consumes: `PageScraper` from Task 1 (`from .page_scraper import PageScraper`), exactly as defined there (`collect(on_done, on_progress=None)`, `stop()`).
- Produces (consumed by Task 3): `BookSelectionDialog` class with:
  - `BookSelectionDialog(browser, resource_labels: dict[str, str], parent=None)` — `resource_labels` maps `resource_type` (e.g. `"book"`) to a display label (e.g. `"Книга"`); the caller passes its own `RESOURCE_LABELS` dict, avoiding a circular import with `main_window.py`.
  - `.exec()` — inherited `QDialog.exec()`; returns `QDialog.DialogCode.Accepted` or `Rejected`.
  - `.selected_items()` → `list[dict]` — the checked items, each `{"resource_type": str, "uuid": str, "title": str}`.
  - `.add_to_calibre()` → `bool`.

- [ ] **Step 1: Write `mybooksmate/book_selection_dialog.py`**

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from .page_scraper import PageScraper


class BookSelectionDialog(QDialog):
    """Modal dialog that lazy-scrolls `browser` to collect every book link on
    the current page (via its own PageScraper), then lets the user check
    which ones to download. Collection starts immediately on construction —
    by the time the caller's exec() pumps the event loop, the scraper's
    timers/JS callbacks are already queued and start firing."""

    def __init__(self, browser, resource_labels, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор книг для скачивания")
        self.resize(480, 560)

        self._resource_labels = resource_labels
        self._items_by_row = []

        layout = QVBoxLayout(self)

        self._status_label = QLabel("Загрузка списка книг…")
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        layout.addWidget(self._progress_bar)

        self._list_widget = QListWidget()
        self._list_widget.itemChanged.connect(self._update_download_button_enabled)
        layout.addWidget(self._list_widget)

        select_buttons = QHBoxLayout()
        self._select_all_button = QPushButton("Выбрать всё")
        self._select_all_button.setEnabled(False)
        self._select_all_button.clicked.connect(self._select_all)
        select_buttons.addWidget(self._select_all_button)

        self._select_none_button = QPushButton("Снять выбор")
        self._select_none_button.setEnabled(False)
        self._select_none_button.clicked.connect(self._select_none)
        select_buttons.addWidget(self._select_none_button)
        layout.addLayout(select_buttons)

        self._calibre_checkbox = QCheckBox("Добавить в Calibre")
        layout.addWidget(self._calibre_checkbox)

        action_buttons = QHBoxLayout()
        self._download_button = QPushButton("Скачать выбранное")
        self._download_button.setEnabled(False)
        self._download_button.clicked.connect(self.accept)
        action_buttons.addWidget(self._download_button)

        cancel_button = QPushButton("Отмена")
        cancel_button.clicked.connect(self.reject)
        action_buttons.addWidget(cancel_button)
        layout.addLayout(action_buttons)

        self._scraper = PageScraper(browser)
        self._scraper.collect(on_done=self._on_collected, on_progress=self._on_progress)

    def reject(self):
        self._scraper.stop()
        super().reject()

    def _on_progress(self, count):
        self._status_label.setText(f"Загрузка списка книг… найдено {count}")

    def _on_collected(self, items):
        self._progress_bar.hide()
        if not items:
            self._status_label.setText("Не удалось найти книги на странице.")
            return

        self._status_label.setText(f"Найдено книг: {len(items)}")
        self._items_by_row = items
        for item in items:
            label = self._resource_labels.get(item["resource_type"], item["resource_type"])
            list_item = QListWidgetItem(f"{label} — {item['title']}")
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            list_item.setCheckState(Qt.CheckState.Unchecked)
            self._list_widget.addItem(list_item)

        self._select_all_button.setEnabled(True)
        self._select_none_button.setEnabled(True)

    def _select_all(self):
        for row in range(self._list_widget.count()):
            self._list_widget.item(row).setCheckState(Qt.CheckState.Checked)

    def _select_none(self):
        for row in range(self._list_widget.count()):
            self._list_widget.item(row).setCheckState(Qt.CheckState.Unchecked)

    def _update_download_button_enabled(self, _changed_item=None):
        any_checked = any(
            self._list_widget.item(row).checkState() == Qt.CheckState.Checked
            for row in range(self._list_widget.count())
        )
        self._download_button.setEnabled(any_checked)

    def selected_items(self):
        return [
            self._items_by_row[row]
            for row in range(self._list_widget.count())
            if self._list_widget.item(row).checkState() == Qt.CheckState.Checked
        ]

    def add_to_calibre(self):
        return self._calibre_checkbox.isChecked()
```

- [ ] **Step 2: Verify dialog UI mechanics with an offscreen script**

This bypasses the real (async, timer-driven) `PageScraper.collect` by calling
the dialog's own `_on_collected` directly with a fixed list — that method
only does synchronous widget updates, so this is a legitimate way to test
the selection/enabling logic without waiting on real timers or a live
browser. Run from the worktree root:

```bash
D:\Projects\MyBooksMate\.venv\Scripts\python.exe -c "
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from mybooksmate.book_selection_dialog import BookSelectionDialog

app = QApplication([])

class StubPage:
    def runJavaScript(self, script, callback=None):
        pass

class StubBrowser:
    def page(self):
        return StubPage()

labels = {'book': 'Книга', 'series': 'Серия'}

# Case 1: normal population + selection mechanics
dialog = BookSelectionDialog(StubBrowser(), labels)
dialog._on_collected([
    {'resource_type': 'book', 'uuid': 'id1', 'title': 'Title One'},
    {'resource_type': 'series', 'uuid': 'id2', 'title': 'Title Two'},
])
assert dialog._list_widget.count() == 2, 'expected 2 list items'
assert dialog.selected_items() == [], 'nothing should be checked initially'
assert dialog._download_button.isEnabled() is False

dialog._select_all()
assert len(dialog.selected_items()) == 2, 'select all should check both'
assert dialog._download_button.isEnabled() is True

dialog._select_none()
assert dialog.selected_items() == []
assert dialog._download_button.isEnabled() is False

dialog._list_widget.item(0).setCheckState(Qt.CheckState.Checked)
selected = dialog.selected_items()
assert selected == [{'resource_type': 'book', 'uuid': 'id1', 'title': 'Title One'}], selected
assert dialog._download_button.isEnabled() is True

assert dialog.add_to_calibre() is False
dialog._calibre_checkbox.setChecked(True)
assert dialog.add_to_calibre() is True

# Case 2: empty collection result
empty_dialog = BookSelectionDialog(StubBrowser(), labels)
empty_dialog._on_collected([])
assert empty_dialog._status_label.text() == 'Не удалось найти книги на странице.'
assert empty_dialog._list_widget.count() == 0
assert empty_dialog._download_button.isEnabled() is False

print('all BookSelectionDialog checks passed')
"
```

Expected output: `all BookSelectionDialog checks passed`. If PySide6 complains about
a missing platform plugin, confirm `QT_QPA_PLATFORM=offscreen` took effect
(the script sets it via `os.environ.setdefault` before importing
`PySide6.QtWidgets`).

- [ ] **Step 3: Bump the debug version**

Read the current value in `mybooksmate/version.py` (left by Task 1) and increment the debug component by 1 again.

- [ ] **Step 4: Mirror the new file and version.py into both release folders**

```bash
cp mybooksmate/book_selection_dialog.py release-Win/mybooksmate/book_selection_dialog.py
cp mybooksmate/book_selection_dialog.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/book_selection_dialog.py"
cp mybooksmate/version.py release-Win/mybooksmate/version.py
cp mybooksmate/version.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
```

- [ ] **Step 5: Commit**

```bash
git add mybooksmate/book_selection_dialog.py mybooksmate/version.py \
  release-Win/mybooksmate/book_selection_dialog.py release-Win/mybooksmate/version.py \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/book_selection_dialog.py" \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
git commit -m "$(cat <<'EOF'
Add BookSelectionDialog: checkable book list for bulk download

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire the button and bulk-download queue into `main_window.py`

**Files:**
- Modify: `mybooksmate/main_window.py`
- Modify: `mybooksmate/version.py` (bump debug version again)
- Mirror (modify): `release-Win/mybooksmate/main_window.py`, `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py`
- Mirror (modify): `release-Win/mybooksmate/version.py`, `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py`

**Interfaces:**
- Consumes: `BookSelectionDialog` from Task 2 (`from .book_selection_dialog import BookSelectionDialog`), exactly as defined there. Also consumes existing `worker.start_download(...)` and `downloader.find_existing_file(...)` unchanged (see `mybooksmate/worker.py` and `mybooksmate/downloader.py` — do not modify either file).
- Produces: nothing consumed by a later task — this is the last code task; Task 4 is docs + manual verification only.

- [ ] **Step 1: Read the current file to confirm nothing has shifted**

Read `mybooksmate/main_window.py` in full before editing — confirm the current content matches what's shown below (Tasks 1/2 don't touch this file, but re-verify line-for-line before making changes, since plans can go stale).

- [ ] **Step 2: Add the new URL patterns**

Add these three module-level constants directly after the existing `URL_PATTERN = re.compile(...)` line:

```python
AUTHOR_BOOKS_PATTERN = re.compile(r"^/authors/[^/]+/author/books/?$")
SECTION_PATTERN = re.compile(r"^/section/[^/]+/[^/?#]+/?$")
SERIES_LIST_PATTERN = re.compile(r"^/series/([^/?#]+)")
```

- [ ] **Step 3: Add the import and the two new Qt widgets needed**

Add this import alongside the other local imports (near `from .settings_dialog import SettingsDialog`):

```python
from .book_selection_dialog import BookSelectionDialog
```

Add `QDialog` to the existing `from PySide6.QtWidgets import (...)` block, inserted alphabetically (between `QComboBox` and `QFrame`).

- [ ] **Step 4: Add the new button to the download panel**

In `_build_download_panel()`, insert this right after the existing
`layout.addWidget(self.download_calibre_button)` line and before
`self.status_label = QLabel("")`:

```python
        self.select_books_button = QPushButton("Выбрать книги...")
        self.select_books_button.clicked.connect(self._start_bulk_selection)
        self.select_books_button.setVisible(False)
        layout.addWidget(self.select_books_button)
```

- [ ] **Step 5: Toggle the button's visibility in `_on_url_changed`**

Replace the current `_on_url_changed` method:

```python
    def _on_url_changed(self, url: QUrl):
        match = URL_PATTERN.search(url.path())
        if not match:
            # Page no longer matches a known book/audiobook/comicbook/series URL —
            # clear the stale ID so a download can't target the wrong book.
            self.uuid_edit.clear()
            return
        segment, resource_id = match.groups()
        resource_type = URL_SEGMENT_TO_RESOURCE.get(segment)
        if not resource_type:
            return
        index = self.type_combo.findData(resource_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self.uuid_edit.setText(resource_id)
```

with:

```python
    def _on_url_changed(self, url: QUrl):
        path = url.path()
        self.select_books_button.setVisible(bool(
            AUTHOR_BOOKS_PATTERN.match(path)
            or SECTION_PATTERN.match(path)
            or SERIES_LIST_PATTERN.match(path)
        ))

        match = URL_PATTERN.search(path)
        if not match:
            # Page no longer matches a known book/audiobook/comicbook/series URL —
            # clear the stale ID so a download can't target the wrong book.
            self.uuid_edit.clear()
            return
        segment, resource_id = match.groups()
        resource_type = URL_SEGMENT_TO_RESOURCE.get(segment)
        if not resource_type:
            return
        index = self.type_combo.findData(resource_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self.uuid_edit.setText(resource_id)
```

- [ ] **Step 6: Add the bulk-selection entry point and queue orchestration**

Add these new methods to `MainWindow`, placed after `_on_download_failed` (the
last method in the class):

```python
    def _start_bulk_selection(self):
        dialog = BookSelectionDialog(self.browser, RESOURCE_LABELS, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run_bulk_queue(dialog.selected_items(), dialog.add_to_calibre())

    def _run_bulk_queue(self, selected, add_to_calibre):
        token = auth.get_auth_token(self.app_dir, self.profile, self)
        if not token:
            QMessageBox.warning(self, "My Books Mate", "Нужна авторизация в Bookmate.")
            return

        self._bulk_token = token
        self._bulk_add_to_calibre = add_to_calibre
        self._bulk_queue = list(selected)
        self._bulk_total = len(selected)
        self._bulk_stats = {"downloaded": 0, "skipped": 0, "failed": 0}
        self.download_button.setEnabled(False)
        self.download_calibre_button.setEnabled(False)
        self.select_books_button.setEnabled(False)
        self._bulk_download_next()

    def _bulk_download_next(self):
        if not self._bulk_queue:
            self.download_button.setEnabled(True)
            self.download_calibre_button.setEnabled(True)
            self.select_books_button.setEnabled(True)
            stats = self._bulk_stats
            self.status_label.setText(
                "Массовое скачивание завершено: "
                f"скачано {stats['downloaded']}, "
                f"пропущено {stats['skipped']}, "
                f"ошибок {stats['failed']}"
            )
            return

        item = self._bulk_queue.pop(0)
        resource_type = item["resource_type"]
        uuid = item["uuid"]
        title = item["title"]
        current_number = self._bulk_total - len(self._bulk_queue)

        try:
            existing_path = downloader.find_existing_file(
                resource_type, uuid, self.config.download_folder, self._bulk_token
            )
        except Exception:  # noqa: BLE001
            existing_path = None

        if existing_path:
            self._bulk_stats["skipped"] += 1
            self._bulk_download_next()
            return

        os.makedirs(self.config.download_folder, exist_ok=True)
        self.status_label.setText(f"Скачивание {current_number} из {self._bulk_total}: {title}")
        item_add_to_calibre = self._bulk_add_to_calibre and resource_type in CALIBRE_COMPATIBLE

        worker.start_download(
            self,
            resource_type,
            uuid,
            self.config.download_folder,
            self._bulk_token,
            self.config.max_bitrate,
            item_add_to_calibre,
            self.config.calibre_path,
            self._on_bulk_item_finished,
            self._on_bulk_item_failed,
            False,
            self.config.convert_to_fb2,
        )

    def _on_bulk_item_finished(self, path, already_downloaded, calibre_message):
        self._bulk_stats["downloaded"] += 1
        self._bulk_download_next()

    def _on_bulk_item_failed(self, message):
        self._bulk_stats["failed"] += 1
        self._bulk_download_next()
```

Note: `worker.start_download` reassigns `parent._download_thread`/
`parent._download_worker` on `self` for each item in the queue (see
`worker.py`'s `start_download`) — this is safe here because downloads are
strictly sequential (the next one only starts from `_on_bulk_item_finished`/
`_on_bulk_item_failed`, which only fire after the previous thread's signals
fire), so there is never more than one bulk-download thread alive at a time
and no risk of one item's thread/worker references overwriting a still-running
one's.

- [ ] **Step 7: Verify the file parses and has no obvious import errors**

```bash
D:\Projects\MyBooksMate\.venv\Scripts\python.exe -c "
import ast
ast.parse(open('mybooksmate/main_window.py', encoding='utf-8').read())
print('main_window.py: syntax OK')
"
D:\Projects\MyBooksMate\.venv\Scripts\python.exe -c "
import mybooksmate.main_window
print('main_window.py: imports OK')
"
```

Expected: both print their OK line. The second command imports the real
module (pulling in `QtWebEngineWidgets` etc.) but does not construct a
`MainWindow` or start `QApplication.exec()`, so it does not open a window or
load any network page — it only proves imports resolve and there's no
top-level syntax/name error.

- [ ] **Step 8: Bump the debug version**

Read the current value in `mybooksmate/version.py` (left by Task 2) and increment the debug component by 1 again.

- [ ] **Step 9: Mirror the changed files into both release folders**

```bash
cp mybooksmate/main_window.py release-Win/mybooksmate/main_window.py
cp mybooksmate/main_window.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py"
cp mybooksmate/version.py release-Win/mybooksmate/version.py
cp mybooksmate/version.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
```

- [ ] **Step 10: Report for manual GUI verification — do not skip**

This task wires together real `QWebEngineView`/`QWebEnginePage` behavior
(JS injection, lazy scroll, a modal dialog nested inside the browser's event
loop) that cannot be exercised by an offscreen script the way Tasks 1-2
were. Per the Global Constraints section's hard-won lesson, end this task's
report with an explicit note: **"Manual GUI verification on real
books.yandex.ru pages has NOT been performed by me — a human must launch the
app and click through the flow on at least one real Author/Series/Section
page before this task can be considered verified end-to-end."** Do not claim
DONE without this caveat.

- [ ] **Step 11: Commit**

```bash
git add mybooksmate/main_window.py mybooksmate/version.py \
  release-Win/mybooksmate/main_window.py release-Win/mybooksmate/version.py \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py" \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
git commit -m "$(cat <<'EOF'
Wire bulk book selection/download into MainWindow

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Manual end-to-end verification + documentation

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the final version number left by Task 3.
- Produces: nothing — this is the last task in the plan.

This task has no code changes. Its job is to get a human to actually click
through the feature on real pages (closing the gap the previous plan on this
repo got burned by), then document what shipped.

- [ ] **Step 1: Request manual verification**

Ask the human partner to launch the app (from the worktree, using the shared
`.venv`, the same way prior manual verification on this repo was done:
`D:\Projects\MyBooksMate\.venv\Scripts\python.exe -m mybooksmate.main` run
from inside the worktree directory) and check, on each of these real pages:

- `https://books.yandex.ru/authors/Sz0Ofnf7/author/books`
- `https://books.yandex.ru/series/enKMfZ71`
- `https://books.yandex.ru/section/all/superhity-SclLTrOc`
- `https://books.yandex.ru/section/all/novinki-l2Cw5xNt`
- `https://books.yandex.ru/section/all/klassika-J2egRejp`

Ask them to confirm:
1. "Выбрать книги..." appears on all 5 pages above, and is hidden again after navigating to a single book page or the homepage.
2. Clicking it opens the dialog, which finishes loading (progress bar disappears, list populates) within a reasonable time, and the found count roughly matches what's visible after manually scrolling the page to the bottom.
3. "Выбрать всё" / "Снять выбор" work.
4. Checking "Добавить в Calibre" and downloading at least one book adds it to Calibre (or is silently skipped for calibre-incompatible types like audiobooks/series without any error).
5. Re-running the same selection afterward skips the already-downloaded item(s) with no confirmation dialog, and the final status line's "пропущено" count reflects it.
6. The final status line's "скачано"/"пропущено"/"ошибок" counts match what was observed.

Do not proceed to Step 2 until the human confirms this passed (or reports issues to fix first — loop back to Task 3 if so).

- [ ] **Step 2: Add a CHANGELOG entry**

Insert at the very top of `docs/CHANGELOG.md` (above the current top-most
entry), using today's actual date and the final version number confirmed in
`mybooksmate/version.py` after Task 3:

```markdown
## 2026-08-27 — Массовое скачивание книг со страниц Автора/Серии/Секции (mybooksmate v1.0.007)
- Новая кнопка "Выбрать книги..." в панели скачивания — видна на страницах Автора (раздел "Книги"), Серии и Секций, скрыта на остальных страницах (`main_window.py`: `AUTHOR_BOOKS_PATTERN`/`SECTION_PATTERN`/`SERIES_LIST_PATTERN`).
- Новый `page_scraper.py`: `PageScraper` лениво докручивает встроенный браузер до конца страницы и через внедрённый JS собирает все ссылки на книги/аудиокниги/комиксы/сериалы/серии по URL-паттерну (без привязки к вёрстке сайта), пока список не перестанет расти.
- Новый `book_selection_dialog.py`: модальный `BookSelectionDialog` со списком найденных книг с чекбоксами, кнопками "Выбрать всё"/"Снять выбор" и чекбоксом "Добавить в Calibre".
- Скачивание выбранных книг идёт последовательно, одна за другой, переиспользуя существующую очередь `worker.start_download`; уже скачанные файлы пропускаются автоматически без диалогов, ошибка одной книги не прерывает очередь.
- Версия `mybooksmate` увеличена до `1.0.007`.
- Проверено вручную на реальных страницах: автор (`/authors/Sz0Ofnf7/author/books`), серия (`/series/enKMfZ71`) и три секции (`superhity`, `novinki`, `klassika`) — кнопка появляется/скрывается корректно, список собирается полностью, выбор и скачивание (включая добавление в Calibre и пропуск уже скачанных) работают как ожидалось.
```

(Replace `1.0.007` with whatever the actual final version number turned out
to be, if it differs, and adjust the last bullet if the human's manual
verification surfaced something noteworthy.)

- [ ] **Step 3: Update README.md if it documents this level of UI detail**

Run:

```bash
grep -n -i "скачива\|кнопк" README.md
```

If README.md has a bullet-list-style "Функциональность" section describing
UI-level features (as it did for the nav-button/context-menu change in the
previous plan on this repo), add a bullet describing the new "Выбрать
книги..." button and where it appears, matching the style/tone of
neighboring bullets. If no such section exists, skip this step.

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md README.md
git commit -m "$(cat <<'EOF'
Document bulk book download feature in CHANGELOG/README

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
