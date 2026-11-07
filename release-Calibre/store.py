"""
The real store implementation, lazily loaded by Calibre via the
`actual_plugin` pointer in the root __init__.py — only imported (and only
imports Qt) once the user actually opens "Get Books" or searches.
"""

import io
import os
import tempfile

from calibre.gui2.store import StorePlugin
from calibre.gui2.store.search_result import SearchResult

from calibre_plugins.yandex_books import api, metadata as book_metadata
from calibre_plugins.yandex_books.config import get_token


class _BookmateDownloadBrowser:
    def __init__(self, browser, token):
        self.browser = browser
        self.token = token

    def __getattr__(self, name):
        return getattr(self.browser, name)

    def open(self, url, *args, **kwargs):
        prefix = f'{api.BASE_URL}/books/'
        suffix = '/content/v4'
        if not (url.startswith(prefix) and url.endswith(suffix)):
            return self.browser.open(url, *args, **kwargs)

        uuid = url[len(prefix):-len(suffix)]
        info = api.get_book_info(uuid, self.token) or {}
        content = api.download_epub_data(uuid, self.token)
        with tempfile.NamedTemporaryFile(suffix='.epub', delete=False) as epub_file:
            epub_path = epub_file.name
            epub_file.write(content)

        try:
            cover_bytes = api.download_cover(info.get('cover_url'), self.token)
            book_metadata.prepare_epub(epub_path, uuid, cover_bytes)
            with open(epub_path, 'rb') as epub_file:
                return io.BytesIO(epub_file.read())
        finally:
            os.remove(epub_path)


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
            if token:
                result.downloads['EPUB'] = api.book_content_url(info['uuid'])
            yield result

    def create_browser(self):
        from calibre import browser

        token = get_token()
        if not token:
            raise RuntimeError('Войдите в аккаунт Bookmate через «Show in store» и повторите поиск.')

        result = browser()
        result.addheaders.extend([
            ('app-user-agent', api.USER_AGENT),
            ('auth-token', token),
        ])
        return _BookmateDownloadBrowser(result, token)

    def open(self, gui=None, parent=None, detail_item=None, external=False):
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
