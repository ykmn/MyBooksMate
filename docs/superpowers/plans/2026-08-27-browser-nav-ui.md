# Browser Nav UI (crupные кнопки + "Копировать ссылку") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the browser navigation buttons (←, →, ⟲, ⌂) large with a colored background and contrasting icons, and add a "Копировать ссылку на страницу" item to the embedded browser's context menu.

**Architecture:** Both changes are confined to `mybooksmate/main_window.py`. Button styling is a QSS stylesheet constant applied to the four existing `QToolButton`s in `_build_browser_container()`. The context menu item is added by installing a custom context menu handler on the `QWebEngineView` that takes Chromium's standard menu and appends one more action + separator.

**Tech Stack:** PySide6 (`QToolButton`, `QSS` stylesheets, `QWebEngineView`, `QMenu`, `QAction`, `QApplication.clipboard()`).

## Global Constraints

- All `.py` source lives under `mybooksmate/`; no top-level `.py` files (per `CLAUDE.md`).
- After editing any file under `mybooksmate/`, immediately copy the updated file into **both** `release-Win/mybooksmate/` and `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/` in the same change (per `CLAUDE.md`).
- Bump the debug component of the version in `mybooksmate/version.py` (`__version__ = "major.minor.debug"`) in the same change as any `mybooksmate/` edit, and copy `version.py` to both release folders too (per `CLAUDE.md` "Версионность").
- Update `docs/CHANGELOG.md` and `README.md` to reflect the change (per `CLAUDE.md` "Update developing history in `docs/` folder as well as README.md on every change").
- No automated test suite exists for this Qt UI code — verification is manual, via the `run` skill (launch the app and interact with it).
- Design doc: `docs/superpowers/specs/2026-08-27-browser-nav-ui-design.md`.

---

### Task 1: Style the navigation buttons (large, colored, contrasting)

**Files:**
- Modify: `mybooksmate/main_window.py:103-137` (`_build_browser_container`)
- Modify: `mybooksmate/version.py:7` (bump debug version)
- Modify (mirror): `release-Win/mybooksmate/main_window.py`, `release-Win/mybooksmate/version.py`
- Modify (mirror): `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py`, `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py`

**Interfaces:**
- Consumes: nothing new — reuses existing `self.browser` (`QWebEngineView`) already created before `_build_browser_container()` is called in `__init__`.
- Produces: a module-level constant `NAV_BUTTON_STYLE` (a QSS string) that Task 2 does not need but should not remove.

- [ ] **Step 1: Read the current implementation to confirm line numbers are still accurate**

Open `mybooksmate/main_window.py` and confirm `_build_browser_container` still matches the design doc's description (lines may have shifted slightly if the file changed since this plan was written). Use the actual current content as ground truth, not the line numbers below.

- [ ] **Step 2: Add the QSS style constant**

Add this near the top of `mybooksmate/main_window.py`, after the existing module-level constants (`URL_PATTERN = ...`):

```python
NAV_BUTTON_STYLE = """
QToolButton {
    background-color: #2f7ff2;
    color: #ffffff;
    font-size: 18px;
    font-weight: bold;
    min-width: 44px;
    min-height: 36px;
    border: none;
    border-radius: 6px;
    padding: 2px;
}
QToolButton:hover {
    background-color: #1f6fe0;
}
QToolButton:pressed {
    background-color: #175bc0;
}
"""
```

- [ ] **Step 3: Apply the style to all four nav buttons**

In `_build_browser_container()`, after each of the four `QToolButton()` instantiations
(`back_button`, `forward_button`, `reload_button`, `home_button`) and before they're
added to `nav_bar`, add a call to `setStyleSheet(NAV_BUTTON_STYLE)`. Concretely, change:

```python
        back_button = QToolButton()
        back_button.setText("←")
        back_button.setToolTip("Назад")
        back_button.clicked.connect(self.browser.back)
        nav_bar.addWidget(back_button)

        forward_button = QToolButton()
        forward_button.setText("→")
        forward_button.setToolTip("Вперёд")
        forward_button.clicked.connect(self.browser.forward)
        nav_bar.addWidget(forward_button)

        reload_button = QToolButton()
        reload_button.setText("⟲")
        reload_button.setToolTip("Обновить")
        reload_button.clicked.connect(self.browser.reload)
        nav_bar.addWidget(reload_button)

        home_button = QToolButton()
        home_button.setText("⌂")
        home_button.setToolTip("На главную (books.yandex.ru)")
        home_button.clicked.connect(lambda: self.browser.setUrl(QUrl(START_URL)))
        nav_bar.addWidget(home_button)
```

to:

```python
        back_button = QToolButton()
        back_button.setText("←")
        back_button.setToolTip("Назад")
        back_button.setStyleSheet(NAV_BUTTON_STYLE)
        back_button.clicked.connect(self.browser.back)
        nav_bar.addWidget(back_button)

        forward_button = QToolButton()
        forward_button.setText("→")
        forward_button.setToolTip("Вперёд")
        forward_button.setStyleSheet(NAV_BUTTON_STYLE)
        forward_button.clicked.connect(self.browser.forward)
        nav_bar.addWidget(forward_button)

        reload_button = QToolButton()
        reload_button.setText("⟲")
        reload_button.setToolTip("Обновить")
        reload_button.setStyleSheet(NAV_BUTTON_STYLE)
        reload_button.clicked.connect(self.browser.reload)
        nav_bar.addWidget(reload_button)

        home_button = QToolButton()
        home_button.setText("⌂")
        home_button.setToolTip("На главную (books.yandex.ru)")
        home_button.setStyleSheet(NAV_BUTTON_STYLE)
        home_button.clicked.connect(lambda: self.browser.setUrl(QUrl(START_URL)))
        nav_bar.addWidget(home_button)
```

- [ ] **Step 4: Bump the debug version**

In `mybooksmate/version.py`, change `__version__ = "1.0.001"` to `__version__ = "1.0.002"` (bump the debug component by 1 — confirm the current value first since it may have moved since this plan was written, and increment whatever it currently is).

- [ ] **Step 5: Mirror both changed files into both release folders**

```bash
cp mybooksmate/main_window.py release-Win/mybooksmate/main_window.py
cp mybooksmate/main_window.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py"
cp mybooksmate/version.py release-Win/mybooksmate/version.py
cp mybooksmate/version.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
```

- [ ] **Step 6: Manually verify with the `run` skill**

Launch the app. Confirm:
- the four nav buttons (←, →, ⟲, ⌂) are visibly larger than before, with a blue background and white text;
- hovering darkens the background slightly, pressing darkens it further;
- clicking each button still performs its function (Back/Forward navigate history, ⟲ reloads, ⌂ goes to `https://books.yandex.ru/`);
- the window title bar shows the bumped version number (e.g. `My Books Mate v1.0.002`).

- [ ] **Step 7: Commit**

```bash
git add mybooksmate/main_window.py mybooksmate/version.py \
  release-Win/mybooksmate/main_window.py release-Win/mybooksmate/version.py \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py" \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
git commit -m "$(cat <<'EOF'
Make browser nav buttons large with colored background

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add "Копировать ссылку на страницу" to the browser context menu

**Files:**
- Modify: `mybooksmate/main_window.py` (imports, `__init__`, new handler method)
- Modify: `mybooksmate/version.py:7` (bump debug version again)
- Modify (mirror): `release-Win/mybooksmate/main_window.py`, `release-Win/mybooksmate/version.py`
- Modify (mirror): `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py`, `release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py`

**Interfaces:**
- Consumes: `self.browser` (`QWebEngineView`, created in `__init__` before `_build_browser_container()` is called).
- Produces: a new `MainWindow._show_browser_context_menu(self, pos)` method wired to `self.browser.customContextMenuRequested`. Nothing later in the codebase depends on this method's name, but keep it if extending the menu further later.

- [ ] **Step 1: Add required imports**

In `mybooksmate/main_window.py`, add `QAction` to the imports. `QAction` in PySide6 lives in `QtGui`, not `QtWidgets`. Add a new import line near the existing `PySide6.QtCore` import:

```python
from PySide6.QtGui import QAction
```

Also add `QApplication` to the existing `from PySide6.QtWidgets import (...)` block (it's needed to reach the clipboard) — insert `QApplication` alphabetically into that import list, e.g. right before `QComboBox`.

- [ ] **Step 2: Enable a custom context menu on the browser and wire the handler**

In `__init__`, right after the existing line:

```python
        self.browser.urlChanged.connect(self._on_url_changed)
```

add:

```python
        self.browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.browser.customContextMenuRequested.connect(self._show_browser_context_menu)
```

This requires `Qt` from `PySide6.QtCore` — add `Qt` to the existing `from PySide6.QtCore import QUrl` line, making it `from PySide6.QtCore import QUrl, Qt`.

- [ ] **Step 3: Implement the handler method**

Add this new method to `MainWindow`, near `_on_url_changed` (e.g. directly after it):

```python
    def _show_browser_context_menu(self, pos):
        menu = self.browser.page().createStandardContextMenu()
        menu.addSeparator()
        copy_link_action = QAction("Копировать ссылку на страницу", menu)
        copy_link_action.triggered.connect(self._copy_page_link)
        menu.addAction(copy_link_action)
        menu.exec(self.browser.mapToGlobal(pos))

    def _copy_page_link(self):
        QApplication.clipboard().setText(self.browser.url().toString())
```

- [ ] **Step 4: Bump the debug version again**

In `mybooksmate/version.py`, bump the debug component by 1 again from whatever Task 1 left it at (e.g. `1.0.002` → `1.0.003`).

- [ ] **Step 5: Mirror both changed files into both release folders**

```bash
cp mybooksmate/main_window.py release-Win/mybooksmate/main_window.py
cp mybooksmate/main_window.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py"
cp mybooksmate/version.py release-Win/mybooksmate/version.py
cp mybooksmate/version.py "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
```

- [ ] **Step 6: Manually verify with the `run` skill**

Launch the app. Confirm:
- right-clicking anywhere in the embedded browser shows the usual Chromium menu items (Назад, Вперёд, Обновить, etc. — whatever Chromium normally offers there) followed by a separator and "Копировать ссылку на страницу";
- clicking "Копировать ссылку на страницу" and then pasting (e.g. into the "ID книги" field or any text editor) shows the current page's URL;
- navigating to a different page and repeating shows the new URL, confirming it reads live state rather than a stale value.

- [ ] **Step 7: Commit**

```bash
git add mybooksmate/main_window.py mybooksmate/version.py \
  release-Win/mybooksmate/main_window.py release-Win/mybooksmate/version.py \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/main_window.py" \
  "release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/version.py"
git commit -m "$(cat <<'EOF'
Add "copy page link" item to browser context menu

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Update documentation (CHANGELOG + README)

**Files:**
- Modify: `docs/CHANGELOG.md` (prepend a new dated entry at the top, above the existing most-recent entry)
- Modify: `README.md` (mention the new context menu item if the README documents browser controls)

**Interfaces:**
- Consumes: the final version number left by Task 2 (e.g. `1.0.003`).
- Produces: nothing consumed by other tasks — this is the last task in the plan.

- [ ] **Step 1: Add a CHANGELOG entry**

Open `docs/CHANGELOG.md` and insert a new entry at the very top (above the `## 2026-06-24 — release-Mac: ...` entry), using today's actual date and the final version number from Task 2:

```markdown
## 2026-08-27 — Крупные кнопки навигации браузера + "Копировать ссылку на страницу" (mybooksmate v1.0.003)
- Кнопки навигации браузера (←, →, ⟲, ⌂) в `main_window.py` увеличены и получили единый акцентный цвет фона с контрастным текстом (`NAV_BUTTON_STYLE`), вместо мелких однотонных `QToolButton` без стиля.
- В контекстное меню встроенного браузера добавлен пункт "Копировать ссылку на страницу" (в конец, после стандартных пунктов Chromium) — копирует текущий URL страницы в буфер обмена.
- Версия `mybooksmate` увеличена до `1.0.003`.
```

(Replace `1.0.003` with whatever the actual final version number from Task 2 turned out to be, if it differs.)

- [ ] **Step 2: Check whether README.md documents browser controls, and update if so**

Run:

```bash
grep -n -i "браузер\|кнопк" README.md
```

If the README has a bullet list describing the embedded browser's features (e.g. near "встроенный браузер"), add a short bullet mentioning the larger nav buttons and the "Копировать ссылку на страницу" context menu item, matching the style/tone of neighboring bullets. If the README doesn't describe UI controls at this level of detail anywhere, skip this step — don't invent a new section that doesn't match the doc's existing structure.

- [ ] **Step 3: Commit**

```bash
git add docs/CHANGELOG.md README.md
git commit -m "$(cat <<'EOF'
Document browser nav UI changes in CHANGELOG/README

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
