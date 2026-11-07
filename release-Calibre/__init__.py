"""
Calibre plugin descriptor for the "Яндекс.Книги" store.

This file is imported by Calibre in every context (GUI, headless server,
command line conversion, etc.), so it must stay free of any Qt/GUI imports
at module level — the real implementation (which needs Qt) lives in
store.py and is loaded lazily by Calibre only when the store is actually
used, via the `actual_plugin` pointer below.

Version scheme: see "Версионность" in CLAUDE.md — major.minor.debug, e.g.
(1, 0, 0) == "1.0.000". Bump the third (debug) number on every change.
"""

from calibre.customize import StoreBase


class YandexBooksStore(StoreBase):
    name = 'Яндекс.Книги'
    description = ('Поиск, авторизация и скачивание книг с books.yandex.ru '
                   '(через Bookmate) прямо в библиотеку Calibre.')
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'My Books Mate'
    version = (1, 0, 6)
    minimum_calibre_version = (5, 0, 0)
    type = _('Store')

    formats = ['EPUB']
    affiliate = False
    headquarters = 'RU'

    actual_plugin = 'calibre_plugins.yandex_books.store:YandexBooksStorePlugin'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.yandex_books.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
