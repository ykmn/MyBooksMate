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
