"""
OAuth login dialog. Imports Qt at module level on purpose — this module is
only ever imported lazily from store.py (the actual_plugin implementation),
never from the root __init__.py, so Qt is guaranteed to be available here.
"""

import urllib.parse

from qt.core import QDialog, QUrl, QVBoxLayout
from qt.webengine import QWebEnginePage, QWebEngineView

from calibre_plugins.yandex_books.api import OAUTH_NETLOC, OAUTH_URL
from calibre_plugins.yandex_books.config import get_token, set_token


class OAuthDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Вход в аккаунт Bookmate')
        self.resize(480, 640)
        self.token = None

        self.view = QWebEngineView(self)
        self.view.setPage(QWebEnginePage(self.view))
        self.view.urlChanged.connect(self._on_url_changed)
        self.view.load(QUrl(OAUTH_URL))

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

    def _on_url_changed(self, url):
        if url.host() == OAUTH_NETLOC:
            fragment = urllib.parse.urlparse(url.toString()).fragment
            params = urllib.parse.parse_qs(fragment)
            if 'access_token' in params:
                self.token = params['access_token'][0]
                self.accept()


def ensure_auth_token(parent=None):
    """Returns the saved token, or shows the login dialog and saves/returns
    the new one. Returns None if the user closed the dialog without
    logging in."""
    token = get_token()
    if token:
        return token

    dialog = OAuthDialog(parent)
    dialog.exec_()
    if dialog.token:
        set_token(dialog.token)
        return dialog.token
    return None
