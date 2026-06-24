import os
import urllib.parse

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

OAUTH_URL = "https://oauth.yandex.ru/authorize?response_type=token&client_id=4483e97bab6e486a9822973109a14d05"
OAUTH_NETLOC = "yx4483e97bab6e486a9822973109a14d05.oauth.yandex.ru"
TOKEN_FILE = "token.txt"


class OAuthDialog(QDialog):
    """Logs in to the Bookmate API. Reuses the main browser's persistent profile so
    the Yandex Passport login performed here also signs in the embedded browser
    session on books.yandex.ru (same cookie storage)."""

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход в аккаунт Bookmate")
        self.resize(480, 640)
        self.token = None

        self.view = QWebEngineView(self)
        self.view.setPage(QWebEnginePage(profile, self.view))
        self.view.urlChanged.connect(self._on_url_changed)
        self.view.load(QUrl(OAUTH_URL))

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

    def _on_url_changed(self, url: QUrl):
        if url.host() == OAUTH_NETLOC:
            fragment = urllib.parse.urlparse(url.toString()).fragment
            params = urllib.parse.parse_qs(fragment)
            if "access_token" in params:
                self.token = params["access_token"][0]
                self.accept()


def get_token_path(app_dir):
    return os.path.join(app_dir, TOKEN_FILE)


def get_auth_token(app_dir, profile, parent=None):
    token_path = get_token_path(app_dir)
    if os.path.isfile(token_path):
        with open(token_path, encoding="utf-8") as file:
            token = file.read().strip()
            if token:
                return token

    dialog = OAuthDialog(profile, parent)
    dialog.exec()
    if not dialog.token:
        return None

    with open(token_path, "w", encoding="utf-8") as file:
        file.write(dialog.token)
    return dialog.token


def reset_auth_token(app_dir):
    token_path = get_token_path(app_dir)
    if os.path.isfile(token_path):
        os.remove(token_path)
