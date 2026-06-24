"""
Minimal, stdlib-only client for searching and downloading books from
books.yandex.ru / Bookmate. Deliberately avoids third-party dependencies
(httpx, bs4, ...) so the plugin doesn't need to vendor anything into the
zip Calibre loads.

Search uses the site's own GraphQL backend (https://books.yandex.ru/node-api/
p-graphql/) — captured from a real browser session via DevTools "Copy as
cURL" — instead of scraping the search results page: the page is a Next.js
app that renders search results client-side, so the static HTML only
contains unrelated "recommended" books, not actual query matches. The
GraphQL endpoint enforces a query allow-list (rejects any query text it
doesn't recognize with "Whitelist: query not found"), so the query document
below must stay byte-identical to what the real frontend sends — do not
"clean up" or reformat it.

Scope: text books only (resource type "book" -> EPUB). Audiobooks, comics,
serials and series use different download endpoints and aren't supported
by this plugin yet.
"""

import json
import time
import urllib.error
import urllib.request

BASE_URL = "https://api.bookmate.yandex.net/api/v5"
BOOKS_PAGE_URL = "https://books.yandex.ru/books/{uuid}"
GRAPHQL_URL = "https://books.yandex.ru/node-api/p-graphql/"

OAUTH_URL = ("https://oauth.yandex.ru/authorize?response_type=token"
             "&client_id=4483e97bab6e486a9822973109a14d05")
OAUTH_NETLOC = "yx4483e97bab6e486a9822973109a14d05.oauth.yandex.ru"

USER_AGENT = "Samsung/Galaxy_A51 Android/12 Bookmate/3.7.3"

# Captured verbatim (whitelisted) from a real books.yandex.ru search request.
SEARCH_QUERY = """query Search($search: String!, $cursor: String!, $type: Type, $noMisspell: Boolean) {
  search(
    query: {cursor: $cursor, query: $search, type: $type, noMisspell: $noMisspell}
  ) {
    cursor
    misspell {
      ...FSearchMisspellItem
      __typename
    }
    page {
      ...FSearchItem
      __typename
    }
    __typename
  }
}

fragment FSearchCover on Cover {
  url
  ratio
  backgroundColorHex
  __typename
}

fragment FSearchUser on User {
  name
  uuid
  login
  followersCount
  avatar {
    ...FSearchCover
    __typename
  }
  __typename
}

fragment FSearchTopic on Topic {
  name
  uuid
  totalBook
  slug
  parent {
    slug
    name
    __typename
  }
  __typename
}

fragment FSearchBookPerson on Person {
  uuid
  name
  hidden
  __typename
}

fragment FSearchSeries on Series {
  uuid
  name
  cover {
    ...FSearchCover
    __typename
  }
  items {
    total
    followersCount
    __typename
  }
  authors {
    ...FSearchBookPerson
    __typename
  }
  __typename
}

fragment FSearchPerson on Person {
  name
  uuid
  roles
  worksCount
  author {
    totalBook
    __typename
  }
  narrator {
    totalBook
    __typename
  }
  translator {
    totalBook
    __typename
  }
  avatar {
    ...FSearchCover
    __typename
  }
  __typename
}

fragment FBookSearch on Book {
  initUuid
  name
  cover {
    ...FSearchCover
    __typename
  }
  authors {
    ...FSearchBookPerson
    __typename
  }
  __typename
}

fragment FBookSearchItem on Book {
  ...FBookSearch
  tags {
    name
    value
    __typename
  }
  __typename
}

fragment FSearchBookProgress on Progress {
  inLibrary
  finished
  progress
  __typename
}

fragment FSearchAvailability on Availability {
  ageRestriction {
    name
    value
    __typename
  }
  __typename
}

fragment FSearchTextBook on TextBook {
  readersCount
  book {
    ...FBookSearchItem
    __typename
  }
  progress {
    ...FSearchBookProgress
    __typename
  }
  availability {
    ...FSearchAvailability
    __typename
  }
  __typename
}

fragment FSearchAudioBook on AudioBook {
  listenersCount
  book {
    ...FBookSearchItem
    __typename
  }
  narrators {
    ...FSearchBookPerson
    __typename
  }
  progress {
    ...FSearchBookProgress
    __typename
  }
  availability {
    ...FSearchAvailability
    __typename
  }
  __typename
}

fragment FSearchComicBook on ComicBook {
  readersCount
  book {
    ...FBookSearchItem
    __typename
  }
  progress {
    ...FSearchBookProgress
    __typename
  }
  availability {
    ...FSearchAvailability
    __typename
  }
  __typename
}

fragment FSearchBookshelf on Bookshelf {
  uuid
  name
  followersCount
  cover {
    ...FSearchCover
    __typename
  }
  description
  postsCount
  user {
    uuid
    avatar {
      ...FSearchCover
      __typename
    }
    name
    __typename
  }
  availability {
    ageRestriction {
      value
      __typename
    }
    __typename
  }
  __typename
}

fragment FSearchPublisher on Publisher {
  name
  uuid
  worksCount
  avatar {
    ...FSearchCover
    __typename
  }
  __typename
}

fragment FSearchTextSerial on TextSerial {
  readersCount
  book {
    ...FBookSearchItem
    __typename
  }
  episodes {
    total
    __typename
  }
  progress {
    ...FSearchBookProgress
    __typename
  }
  availability {
    ageRestriction {
      name
      value
      __typename
    }
    __typename
  }
  __typename
}

fragment FSearchMisspellItem on MisspellItem {
  correctedText
  correctionType
  __typename
}

fragment FSearchItem on SearchItem {
  ...FSearchUser
  ...FSearchTopic
  ...FSearchSeries
  ...FSearchPerson
  ...FSearchTextBook
  ...FSearchAudioBook
  ...FSearchComicBook
  ...FSearchBookshelf
  ...FSearchPublisher
  ...FSearchTextSerial
  __typename
}"""


def _headers(auth_token=''):
    return {
        'app-user-agent': USER_AGENT,
        'auth-token': auth_token or '',
        'user-agent': 'Mozilla/5.0',
    }


def _fetch(url, auth_token='', timeout=20, retries=3):
    request = urllib.request.Request(url, headers=_headers(auth_token))
    last_error = None
    for _attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            last_error = exc
            time.sleep(2)
    raise last_error


MAX_SEARCH_PAGES = 10  # safety cap — ~25 items/page, mixed result types


def _search_page(query, cursor, auth_token, timeout):
    body = json.dumps({
        'operationName': 'Search',
        'variables': {'search': query, 'cursor': cursor, 'noMisspell': False},
        'extensions': {'clientLibrary': {'name': '@apollo/client', 'version': '4.0.12'}},
        'query': SEARCH_QUERY,
    }).encode('utf-8')

    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        method='POST',
        headers={
            'accept': 'application/graphql-response+json,application/json;q=0.9',
            'content-type': 'application/json',
            'app-language': 'ru',
            'origin': 'https://books.yandex.ru',
            'referer': 'https://books.yandex.ru/search/all/',
            'user-agent': 'Mozilla/5.0',
            'user-is-authorized': 'true' if auth_token else 'false',
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    return (payload.get('data') or {}).get('search') or {}


def search_books(query, auth_token='', max_results=10, timeout=20):
    """Searches via books.yandex.ru's GraphQL backend and returns text-book
    results (other result types — audiobooks, people, series, ... — are
    filtered out, see module docstring for scope). Results are paginated
    ~25 items/page (mixed types), so multiple pages are fetched — following
    the "cursor" the API returns — until max_results text books are found,
    a page comes back empty, or the cursor stops advancing."""
    results = []
    cursor = ''
    for _page_num in range(MAX_SEARCH_PAGES):
        try:
            search = _search_page(query, cursor, auth_token, timeout)
        except Exception:
            break

        page = search.get('page') or []
        if not page:
            break

        for item in page:
            if item.get('__typename') != 'TextBook':
                continue
            book = item.get('book') or {}
            uuid = book.get('initUuid')
            if not uuid:
                continue
            authors = ', '.join(
                author.get('name', '')
                for author in (book.get('authors') or [])
                if author.get('name')
            )
            results.append({
                'uuid': uuid,
                'title': book.get('name') or uuid,
                'authors': authors,
                'cover_url': (book.get('cover') or {}).get('url', ''),
                'detail_url': BOOKS_PAGE_URL.format(uuid=uuid),
            })
            if len(results) >= max_results:
                return results

        new_cursor = search.get('cursor')
        if not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor

    return results


def get_book_info(uuid, auth_token='', timeout=20):
    try:
        data = json.loads(_fetch(f"{BASE_URL}/books/{uuid}", auth_token, timeout))
    except Exception:
        return None

    book = data.get('book') if isinstance(data, dict) else None
    if not book:
        return None

    authors = _extract_authors(book.get('authors'))

    return {
        'uuid': uuid,
        'title': book.get('title') or uuid,
        'authors': authors,
        'cover_url': (book.get('cover') or {}).get('large', ''),
        'detail_url': BOOKS_PAGE_URL.format(uuid=uuid),
    }


def _extract_authors(authors):
    """The Bookmate API returns "authors" as either a plain string or a
    list of {"name": ...} dicts (and sometimes a list of plain strings),
    depending on the resource."""
    if isinstance(authors, list):
        names = []
        for author in authors:
            if isinstance(author, dict) and author.get('name'):
                names.append(author['name'])
            elif isinstance(author, str) and author:
                names.append(author)
        return ', '.join(names)
    if isinstance(authors, str):
        return authors
    return ''


def download_epub(uuid, auth_token, destination_path, timeout=120):
    content_url = f"{BASE_URL}/books/{uuid}/content/v4"
    data = _fetch(content_url, auth_token, timeout, retries=3)
    with open(destination_path, 'wb') as file:
        file.write(data)
    return destination_path


def download_cover(cover_url, timeout=20):
    """Returns the cover image bytes, or None if cover_url is empty or the
    download fails (the caller treats a missing cover as non-fatal)."""
    if not cover_url:
        return None
    try:
        request = urllib.request.Request(cover_url, headers={'user-agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception:
        return None
