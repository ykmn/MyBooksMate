import os
import platform
import re
import subprocess

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from . import auth, downloader, worker
from .config import AppConfig
from .settings_dialog import SettingsDialog
from .version import __version__

START_URL = "https://books.yandex.ru/"

# Maps a books.yandex.ru URL path segment to the resource_type used by RUBookmatedownloader
URL_SEGMENT_TO_RESOURCE = {
    "books": "book",
    "audiobooks": "audiobook",
    "comicbooks": "comicbook",
    "serial": "serial",
    "series": "series",
}

CALIBRE_COMPATIBLE = {"book", "comicbook", "serial"}

RESOURCE_LABELS = {
    "book": "Книга",
    "audiobook": "Аудиокнига",
    "comicbook": "Комикс",
    "serial": "Сериал (книга по частям)",
    "series": "Серия",
}

URL_PATTERN = re.compile(r"/(books|audiobooks|comicbooks|serial|series)/([^/?#]+)")

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"My Books Mate v{__version__}")
        self.resize(1280, 800)

        self.config = AppConfig()
        self.app_dir = os.path.dirname(self.config.path)

        saved_geometry = self.config.window_geometry
        if saved_geometry:
            self.restoreGeometry(saved_geometry)

        self.profile = self._build_persistent_profile()
        self.browser = QWebEngineView(self)
        self.browser.setPage(QWebEnginePage(self.profile, self.browser))
        self.browser.load(QUrl(START_URL))
        self.browser.urlChanged.connect(self._on_url_changed)

        self.browser_container = self._build_browser_container()
        self.panel = self._build_download_panel()

        self.splitter = QSplitter(self)
        self.splitter.addWidget(self.browser_container)
        self.splitter.addWidget(self.panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        saved_sizes = self.config.splitter_sizes
        if saved_sizes and len(saved_sizes) == 2:
            self.splitter.setSizes(saved_sizes)
        self.setCentralWidget(self.splitter)

    def closeEvent(self, event):
        self.config.splitter_sizes = self.splitter.sizes()
        self.config.window_geometry = self.saveGeometry()
        super().closeEvent(event)

    def _build_persistent_profile(self):
        # Explicit storage path tied to the app folder so the login session
        # (cookies) survives between runs regardless of which python.exe
        # launched the app (Qt's implicit default profile path can differ
        # depending on the executable that hosts the process).
        profile_dir = os.path.join(self.app_dir, "webengine_profile")
        os.makedirs(profile_dir, exist_ok=True)
        profile = QWebEngineProfile("MyBooksMate", self)
        profile.setPersistentStoragePath(profile_dir)
        profile.setCachePath(os.path.join(profile_dir, "cache"))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        return profile

    def _build_browser_container(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        nav_bar = QHBoxLayout()
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

        nav_bar.addStretch()
        layout.addLayout(nav_bar)
        layout.addWidget(self.browser)
        return container

    def _build_download_panel(self):
        panel = QWidget(self)
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("Скачивание книги"))

        self.type_combo = QComboBox()
        for key, label in RESOURCE_LABELS.items():
            self.type_combo.addItem(label, key)
        layout.addWidget(QLabel("Тип:"))
        layout.addWidget(self.type_combo)

        self.uuid_edit = QLineEdit()
        self.uuid_edit.setPlaceholderText("ID книги")
        layout.addWidget(QLabel("ID (определяется по странице, можно править):"))
        layout.addWidget(self.uuid_edit)

        self.download_button = QPushButton("Скачать")
        self.download_button.clicked.connect(lambda: self._download(add_to_calibre=False))
        layout.addWidget(self.download_button)

        self.download_calibre_button = QPushButton("Скачать и добавить в Calibre")
        self.download_calibre_button.clicked.connect(lambda: self._download(add_to_calibre=True))
        layout.addWidget(self.download_calibre_button)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        settings_button = QPushButton("Настройки")
        settings_button.clicked.connect(self._open_settings)
        layout.addWidget(settings_button)

        open_folder_button = QPushButton("Открыть папку со скачанными файлами")
        open_folder_button.clicked.connect(self._open_download_folder)
        layout.addWidget(open_folder_button)

        layout.addStretch()
        return panel

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

    def _open_settings(self):
        SettingsDialog(self.config, self).exec()

    def _open_download_folder(self):
        folder = self.config.download_folder
        os.makedirs(folder, exist_ok=True)
        system = platform.system()
        if system == "Windows":
            os.startfile(folder)
        elif system == "Darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)

    def _download(self, add_to_calibre):
        resource_type = self.type_combo.currentData()
        uuid = self.uuid_edit.text().strip()
        if not uuid:
            self.status_label.setText("Не удалось определить ID книги. Откройте страницу книги или введите ID вручную.")
            return
        if add_to_calibre and resource_type not in CALIBRE_COMPATIBLE:
            QMessageBox.warning(self, "My Books Mate", "Добавление в Calibre поддерживается только для книг, комиксов и сериалов.")
            return
        if add_to_calibre and not self.config.calibre_path:
            QMessageBox.warning(self, "My Books Mate", "Укажите путь к Calibre в настройках.")
            return

        token = auth.get_auth_token(self.app_dir, self.profile, self)
        if not token:
            QMessageBox.warning(self, "My Books Mate", "Нужна авторизация в Bookmate.")
            return

        force = False
        try:
            existing_path = downloader.find_existing_file(resource_type, uuid, self.config.download_folder, token)
        except Exception as exc:  # noqa: BLE001
            existing_path = None
            self.status_label.setText(f"Не удалось проверить, скачана ли книга ранее: {exc}")

        if existing_path:
            box = QMessageBox(self)
            box.setWindowTitle("My Books Mate")
            box.setText(f"Книга уже скачана:\n{existing_path}\n\nСкачать заново или пропустить скачивание?")
            redownload_button = box.addButton("Скачать заново", QMessageBox.ButtonRole.AcceptRole)
            skip_button = box.addButton("Пропустить", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(skip_button)
            box.exec()
            force = box.clickedButton() is redownload_button

        os.makedirs(self.config.download_folder, exist_ok=True)
        self.status_label.setText("Скачивание...")
        self.download_button.setEnabled(False)
        self.download_calibre_button.setEnabled(False)

        worker.start_download(
            self,
            resource_type,
            uuid,
            self.config.download_folder,
            token,
            self.config.max_bitrate,
            add_to_calibre,
            self.config.calibre_path,
            self._on_download_finished,
            self._on_download_failed,
            force,
            self.config.convert_to_fb2,
        )

    def _on_download_finished(self, path, already_downloaded, calibre_message):
        self.download_button.setEnabled(True)
        self.download_calibre_button.setEnabled(True)
        if not path:
            message = "Готово"
        elif already_downloaded:
            message = f"Книга уже была скачана ранее: {path}"
        else:
            message = f"Готово: {path}"
        if calibre_message:
            message += f"\n{calibre_message}"
        self.status_label.setText(message)

    def _on_download_failed(self, message):
        self.download_button.setEnabled(True)
        self.download_calibre_button.setEnabled(True)
        self.status_label.setText(f"Ошибка: {message}")
        QMessageBox.critical(self, "My Books Mate", message)
