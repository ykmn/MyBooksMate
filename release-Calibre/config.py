from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/yandex_books')
prefs.defaults['auth_token'] = ''


def get_token():
    return prefs.get('auth_token', '') or ''


def set_token(token):
    prefs['auth_token'] = token or ''


def clear_token():
    prefs['auth_token'] = ''


def ConfigWidget():
    # Imports Qt lazily: this function is only ever called by Calibre from
    # the GUI (Preferences > Plugins > customize plugin), never at plugin
    # load time, so it's safe to import Qt here.
    from qt.core import QLabel, QPushButton, QVBoxLayout, QWidget

    class _ConfigWidget(QWidget):
        def __init__(self):
            super().__init__()
            layout = QVBoxLayout(self)

            self.status_label = QLabel()
            layout.addWidget(self.status_label)

            self.login_button = QPushButton('Войти в аккаунт Bookmate')
            self.login_button.clicked.connect(self._login)
            layout.addWidget(self.login_button)

            self.logout_button = QPushButton('Выйти из аккаунта Bookmate')
            self.logout_button.clicked.connect(self._logout)
            layout.addWidget(self.logout_button)

            layout.addStretch()
            self._refresh_status()

        def _refresh_status(self):
            logged_in = bool(get_token())
            status = 'выполнен вход' if logged_in else 'вход не выполнен'
            self.status_label.setText(f'Аккаунт Bookmate: {status}.')
            self.login_button.setEnabled(not logged_in)
            self.logout_button.setEnabled(logged_in)

        def _login(self):
            from calibre_plugins.yandex_books.auth import ensure_auth_token

            ensure_auth_token(self)
            self._refresh_status()

        def _logout(self):
            clear_token()
            self._refresh_status()

        def save_settings(self):
            # Logout takes effect immediately (see _logout); nothing to
            # persist here, but Calibre expects this method to exist.
            pass

    return _ConfigWidget()
