import json
import time

from PySide6.QtCore import QTimer

# Same segment->resource_type mapping as main_window.py's URL_SEGMENT_TO_RESOURCE,
# duplicated here in JS form since this string is injected into the page, not
# imported from Python.
COLLECT_BOOKS_JS = """
(function() {
    var segmentToType = {
        books: "book",
        audiobooks: "audiobook",
        comicbooks: "comicbook",
        serial: "serial",
        series: "series"
    };
    var pattern = /\\/(books|audiobooks|comicbooks|serial|series)\\/([^\\/?#]+)/;
    var seen = {};
    var items = [];
    var anchors = document.querySelectorAll("a[href]");
    for (var i = 0; i < anchors.length; i++) {
        var anchor = anchors[i];
        if (anchor.closest && anchor.closest("header, nav, footer")) { continue; }
        var match = pattern.exec(anchor.getAttribute("href") || "");
        if (!match) { continue; }
        var resourceType = segmentToType[match[1]];
        var uuid = match[2];
        var key = resourceType + ":" + uuid;
        if (seen[key]) { continue; }
        seen[key] = true;
        var title = (anchor.textContent || "").trim();
        if (!title) {
            title = (anchor.getAttribute("aria-label") || anchor.getAttribute("title") || "").trim();
        }
        if (!title) {
            title = uuid;
        }
        items.push({resource_type: resourceType, uuid: uuid, title: title});
    }
    return JSON.stringify({items: items, count: items.length, scrollHeight: document.body.scrollHeight});
})();
"""

TICK_INTERVAL_MS = 500
SETTLE_DELAY_MS = 150
STABLE_TICKS_REQUIRED = 3
MAX_COLLECT_SECONDS = 30


def _is_stable(history):
    """history: list of (count, scroll_height) tuples, oldest first. Returns
    True once the most recent STABLE_TICKS_REQUIRED entries are all identical
    (the lazy-loaded list has stopped growing)."""
    if len(history) < STABLE_TICKS_REQUIRED:
        return False
    return len(set(history[-STABLE_TICKS_REQUIRED:])) == 1


class PageScraper:
    """Lazy-scrolls `browser` to the bottom repeatedly, re-extracting book
    links after each scroll via COLLECT_BOOKS_JS, until the link count and
    document height stop changing (or a timeout elapses). Extraction is
    purely URL-pattern based — no dependency on the site's CSS classes or
    markup, matching main_window.py's own URL_PATTERN/URL_SEGMENT_TO_RESOURCE
    approach."""

    def __init__(self, browser):
        self._browser = browser
        self._history = []
        self._start_time = None
        self._on_done = None
        self._on_progress = None
        self._timer = QTimer()
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def collect(self, on_done, on_progress=None):
        self._on_done = on_done
        self._on_progress = on_progress
        self._history = []
        self._start_time = time.monotonic()
        self._timer.start()
        self._tick()

    def stop(self):
        self._timer.stop()
        self._on_done = None
        self._on_progress = None

    def _tick(self):
        if self._on_done is None:
            return
        self._browser.page().runJavaScript("window.scrollTo(0, document.body.scrollHeight);")
        QTimer.singleShot(SETTLE_DELAY_MS, self._collect_once)

    def _collect_once(self):
        if self._on_done is None:
            return
        self._browser.page().runJavaScript(COLLECT_BOOKS_JS, self._on_collected)

    def _on_collected(self, result):
        if self._on_done is None:
            return
        try:
            parsed = json.loads(result) if result else {}
        except (TypeError, ValueError):
            parsed = {}
        items = parsed.get("items", [])
        count = parsed.get("count", 0)
        scroll_height = parsed.get("scrollHeight", 0)
        self._history.append((count, scroll_height))

        if self._on_progress is not None:
            self._on_progress(count)

        timed_out = (time.monotonic() - self._start_time) >= MAX_COLLECT_SECONDS
        if _is_stable(self._history) or timed_out:
            self._timer.stop()
            on_done = self._on_done
            self._on_done = None
            self._on_progress = None
            on_done(items)
