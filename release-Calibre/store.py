"""
The real store implementation, lazily loaded by Calibre via the
`actual_plugin` pointer in the root __init__.py — only imported (and only
imports Qt) once the user actually opens "Get Books" or searches.
"""

from calibre.gui2.store import StorePlugin
from calibre.gui2.store.search_result import SearchResult

from calibre_plugins.yandex_books import api
from calibre_plugins.yandex_books.config import get_token


class YandexBooksStorePlugin(StorePlugin):
    def search(self, query, max_results=10, timeout=60):
        # Calibre's "Get Books" dialog cleans the combined title/author/
        # keyword query itself before dispatching to stores, and that
        # cleaned query comes through as UTF-8 bytes, not str.
        if isinstance(query, bytes):
            query = query.decode('utf-8')
        token = get_token()
        for info in api.search_books(query, auth_token=token, max_results=max_results, timeout=timeout):
            result = SearchResult()
            result.store_name = self.name
            result.title = info['title']
            result.author = info['authors']
            result.cover_url = info['cover_url']
            result.detail_item = info['uuid']
            result.price = 'Подписка Bookmate'
            result.formats = 'EPUB'
            result.drm = SearchResult.DRM_UNLOCKED
            yield result

    def open(self, parent=None, detail_item=None, external=False):
        from qt.core import QUrl

        from calibre.gui2 import open_url

        if not detail_item:
            return

        if external:
            open_url(QUrl(api.BOOKS_PAGE_URL.format(uuid=detail_item)))
            return

        from calibre_plugins.yandex_books.auth import ensure_auth_token
        from calibre_plugins.yandex_books.download_dialog import DownloadDialog

        token = ensure_auth_token(parent)
        if not token:
            return

        dialog = DownloadDialog(self.gui, detail_item, token, parent)
        dialog.exec_()
