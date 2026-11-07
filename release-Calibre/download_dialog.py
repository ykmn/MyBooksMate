import os
import re
import tempfile

from qt.core import QDialog, QDialogButtonBox, QLabel, QProgressBar, QThread, QVBoxLayout, pyqtSignal

from calibre_plugins.yandex_books import api, metadata as book_metadata

FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|]')


class _DownloadThread(QThread):
    status = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, uuid, token, parent=None):
        super().__init__(parent)
        self.uuid = uuid
        self.token = token

    def run(self):
        try:
            self.status.emit('Скачивание книги...')
            info = api.get_book_info(self.uuid, self.token) or {}
            title = FORBIDDEN_CHARS.sub('', info.get('title') or self.uuid)
            destination = os.path.join(tempfile.gettempdir(), f'{title}.epub')
            api.download_epub(self.uuid, self.token, destination)

            self.status.emit('Обработка обложки и метаданных...')
            cover_bytes = api.download_cover(info.get('cover_url'), self.token)
            book_metadata.prepare_epub(destination, self.uuid, cover_bytes)

            self.finished_ok.emit(destination)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class DownloadDialog(QDialog):
    """Shows download progress, then hands the resulting EPUB to Calibre's
    own "Add Books" action so it lands in the current library."""

    def __init__(self, gui, uuid, token, parent=None):
        super().__init__(parent)
        self.gui = gui
        self.setWindowTitle('Яндекс.Книги')
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        self.label = QLabel('Скачивание книги...')
        layout.addWidget(self.label)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        layout.addWidget(self.buttons)

        self.thread = _DownloadThread(uuid, token, self)
        self.thread.status.connect(self.label.setText)
        self.thread.finished_ok.connect(self._on_finished)
        self.thread.failed.connect(self._on_failed)
        self.thread.start()

    def _on_finished(self, path):
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        try:
            self.gui.iactions['Add Books'].add_filesystem_book(path)
            self.label.setText('Готово: книга добавлена в библиотеку.')
        except Exception as exc:  # noqa: BLE001
            self.label.setText(f'Книга скачана, но не добавлена в библиотеку: {exc}')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def _on_failed(self, message):
        self.progress.setRange(0, 1)
        self.label.setText(f'Ошибка скачивания: {message}')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def closeEvent(self, event):
        # Block closing (via the title-bar X) while the download is still
        # running, so the user can't dismiss the dialog mid-download — the
        # OK button only becomes enabled once the thread is done.
        if self.thread.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
