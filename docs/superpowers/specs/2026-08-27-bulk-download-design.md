# Дизайн: массовое скачивание книг со страниц Автора/Серии/Секции

## Контекст

Сейчас `MainWindow` (`mybooksmate/main_window.py`) умеет скачивать только один
ресурс за раз: URL встроенного браузера автоматически определяет тип и ID
(`URL_PATTERN`, `URL_SEGMENT_TO_RESOURCE`), пользователь жмёт «Скачать» или
«Скачать и добавить в Calibre».

На books.yandex.ru есть страницы со списком книг конечного размера (не
бесконечная лента), где хочется выбрать несколько штук и скачать их разом:

- страница Автора, раздел «Книги»: `https://books.yandex.ru/authors/{id}/author/books`
- страница Серии: `https://books.yandex.ru/series/{id}`
- страницы Секций: `https://books.yandex.ru/section/{category}/{slug}`
  (например `superhity-SclLTrOc`, `novinki-l2Cw5xNt`, `klassika-J2egRejp`)

Список на этих страницах подгружается лениво по скроллу (lazy-scroll), даже
если общее количество книг конечно.

## Требования

1. Кнопка **«Выбрать книги...»** в панели скачивания — видна только на
   подходящих страницах (перечислены выше), на прочих скрыта.
2. По клику — приложение долистывает страницу до конца (lazy-scroll) и
   показывает диалог со списком найденных книг с чекбоксами.
3. В диалоге: **«Выбрать всё» / «Снять выбор»**, чекбокс **«Добавить в
   Calibre»**, кнопки «Скачать выбранное» / «Отмена».
4. Скачивание выбранных книг — последовательно, одна за другой, переиспользуя
   существующую инфраструктуру скачивания. Уже скачанные файлы пропускаются
   автоматически, без диалогов подтверждения. Ошибка одной книги не прерывает
   очередь.

## Дизайн

### 1. Определение страницы и видимость кнопки

Новая кнопка `self.select_books_button` («Выбрать книги...») добавляется в
`_build_download_panel()` между `download_calibre_button` и `status_label`.
Изначально скрыта (`setVisible(False)`).

В `_on_url_changed(url)` добавляется проверка пути URL по трём новым regex
(константы модуля, по аналогии с существующим `URL_PATTERN`):

```python
AUTHOR_BOOKS_PATTERN = re.compile(r"^/authors/[^/]+/author/books/?$")
SECTION_PATTERN = re.compile(r"^/section/[^/]+/[^/?#]+/?$")
SERIES_LIST_PATTERN = re.compile(r"^/series/([^/?#]+)")
```

Если путь совпадает хотя бы с одним из шаблонов — кнопка показывается,
иначе скрывается. `SERIES_LIST_PATTERN` совпадает с тем же URL, что и уже
существующий одиночный ресурс `series` в `URL_PATTERN` — это ожидаемо: на
странице серии одновременно доступны обе функции (авто-заполнение ID для
скачивания серии целиком через существующую панель, и кнопка выбора
отдельных частей серии). Никакого сетевого запроса для определения
пригодности страницы не требуется — только сопоставление пути URL.

### 2. Сбор списка книг со страницы (lazy-scroll + JS)

Новый файл `mybooksmate/page_scraper.py`.

**JS-скрипт** (константа модуля `COLLECT_BOOKS_JS`), исполняемый через
`page.runJavaScript(...)`:
- находит все `<a href>` на странице, чей href матчится по тем же сегментам,
  что и `URL_SEGMENT_TO_RESOURCE` в `main_window.py` (`/books/`,
  `/audiobooks/`, `/comicbooks/`, `/serial/`, `/series/`);
- дедуплицирует по паре `(resource_type, id)`;
- для каждой уникальной ссылки берёт заголовок — текст самой ссылки
  (`textContent`, обрезанный) если он непустой, иначе `title`/`aria-label`
  атрибут ссылки, иначе — сам id (как последний фолбэк, чтобы пункт списка
  никогда не был пустым);
- возвращает JSON-объект `{items: [{resource_type, uuid, title}], count,
  scrollHeight}` — `count` и `scrollHeight` нужны питон-стороне для решения
  «список ещё растёт или уже стабилизировался».

**Класс `PageScraper`**:

```python
class PageScraper:
    def __init__(self, browser: QWebEngineView):
        ...
    def collect(self, on_done):
        """on_done(items: list[dict]) вызывается один раз, когда список стабилизировался."""
```

Реализация — `QTimer` с интервалом ~500 мс:
1. на каждом тике сначала прокручивает страницу вниз
   (`window.scrollTo(0, document.body.scrollHeight)`), затем — через
   отдельный однократный `QTimer.singleShot(150, ...)` (чтобы контент успел
   подгрузиться и отрендериться после скролла) — выполняет
   `COLLECT_BOOKS_JS` и сравнивает `count`/`scrollHeight` с предыдущим
   тиком;
2. если оба значения не менялись 3 тика подряд **или** истёк общий таймаут
   30 секунд — таймер останавливается, выполняется финальный сбор, и
   вызывается `on_done(items)` с итоговым дедуплицированным списком.

Привязки к CSS-классам/вёрстке сайта нет — только структура URL, как и во
всём остальном коде проекта (`URL_PATTERN`). Это делает сборщик устойчивым
к изменению дизайна/классов на books.yandex.ru.

### 3. Диалог выбора книг

Новый файл `mybooksmate/book_selection_dialog.py`, класс
`BookSelectionDialog(QDialog)`.

- Заголовок «Выбор книг для скачивания», модальный.
- Пока список ещё собирается (пока `PageScraper.collect` не вызвал
  колбэк) — виден `QLabel` со статусом («Загрузка списка книг… найдено N»,
  где N обновляется по мере тиков сборщика) и `QProgressBar` в
  неопределённом режиме (`setRange(0, 0)`); кнопки скачивания неактивны.
- После завершения сбора — `QListWidget`, где каждый пункт — чекбокс с
  текстом `"{RESOURCE_LABELS[resource_type]} — {title}"` (переиспользуется
  словарь `RESOURCE_LABELS` из `main_window.py`).
- Кнопки **«Выбрать всё»** / **«Снять выбор»** — массово выставляют/снимают
  `Qt.CheckState.Checked`/`Unchecked` на все пункты списка.
- Чекбокс **«Добавить в Calibre»** (`self.calibre_checkbox`), выключен по
  умолчанию. Не блокирует выбор несовместимых типов (`audiobook`, `series`)
  — при скачивании (Раздел 4) для них флаг Calibre просто игнорируется,
  как и в одиночном режиме (`CALIBRE_COMPATIBLE`).
- Кнопки **«Скачать выбранное»** (disabled, пока не отмечен хотя бы один
  пункт) и **«Отмена»**.
- Публичный API диалога после `exec() == QDialog.DialogCode.Accepted`:
  `dialog.selected_items()` → `list[dict]` (`{resource_type, uuid, title}`)
  и `dialog.add_to_calibre()` → `bool`. Диалог сам скачивание не запускает —
  это делает `MainWindow`.

### 4. Оркестрация массового скачивания

В `main_window.py`:

- `self.select_books_button.clicked.connect(self._start_bulk_selection)`.
- `_start_bulk_selection()`:
  1. блокирует кнопку, выставляет `status_label` в «Загрузка списка книг…»;
  2. создаёт `PageScraper(self.browser)` и вызывает
     `collect(on_done=self._on_books_collected)`.
- `_on_books_collected(items)`:
  - разблокирует кнопку;
  - если `items` пуст — `QMessageBox.warning` («Не удалось найти книги на
    странице») и выход;
  - иначе создаёт `BookSelectionDialog(items, self)` и вызывает `exec()`;
    если результат `Accepted` — забирает `selected_items()`/`add_to_calibre()`
    и вызывает `_run_bulk_queue(...)`.
- `_run_bulk_queue(selected, add_to_calibre)`:
  - запрашивает токен один раз (`auth.get_auth_token`, как в одиночном
    скачивании); при отсутствии токена — предупреждение и выход, очередь не
    стартует;
  - сохраняет очередь в `self._bulk_queue` (список оставшихся элементов) и
    счётчики `self._bulk_stats = {"downloaded": 0, "skipped": 0, "failed": 0}`;
  - блокирует `download_button`/`download_calibre_button`/
    `select_books_button` на время очереди;
  - вызывает `self._bulk_download_next()`.
- `_bulk_download_next()`:
  - если `self._bulk_queue` пуст — восстанавливает кнопки, выводит в
    `status_label` итог («Массовое скачивание завершено: скачано X,
    пропущено Y, ошибок Z») и выходит;
  - иначе `item = self._bulk_queue.pop(0)`; молча проверяет
    `downloader.find_existing_file(item['resource_type'], item['uuid'], ...)`
    — если файл уже существует, инкрементирует `skipped` и рекурсивно (через
    прямой вызов, не через сигнал) переходит к следующему элементу без
    скачивания и без диалога подтверждения;
  - иначе обновляет `status_label` («Скачивание N из M: {title}») и вызывает
    существующий `worker.start_download(...)` с новыми колбэками
    `self._on_bulk_item_finished` / `self._on_bulk_item_failed` — они
    инкрементируют `downloaded`/`failed` соответственно и вызывают
    `self._bulk_download_next()`, продолжая очередь. `worker.py` и
    `downloader.py` не меняются — используются как есть.
- Ошибка одного элемента (`_on_bulk_item_failed`) не показывает модальное
  окно (в отличие от одиночного скачивания) и не прерывает очередь — только
  увеличивает счётчик `failed`, чтобы одна проблемная книга не блокировала
  скачивание остальных выбранных.

## Тестирование

Автотестов для Qt UI в проекте нет (подтверждено ранее) — проверка только
ручная, через `/run`, на реальных страницах из примеров:
- `https://books.yandex.ru/authors/Sz0Ofnf7/author/books`
- `https://books.yandex.ru/series/enKMfZ71`
- `https://books.yandex.ru/section/all/superhity-SclLTrOc`
- `https://books.yandex.ru/section/all/novinki-l2Cw5xNt`
- `https://books.yandex.ru/section/all/klassika-J2egRejp`

Проверить:
- кнопка «Выбрать книги...» появляется на всех 5 страницах и скрывается на
  странице отдельной книги/главной/поиске;
- lazy-scroll действительно долистывает длинный список автора/секции до
  конца (сравнить количество найденных пунктов с тем, что видно на сайте
  после ручного докручивания);
- «Выбрать всё» / «Снять выбор» работают;
- чекбокс «Добавить в Calibre» передаётся в очередь скачивания;
- уже скачанные книги пропускаются без диалогов подтверждения;
- ошибка на одной книге (например, вручную испортить токен на середине
  очереди) не прерывает скачивание остальных;
- итоговая статистика в `status_label` совпадает с ожидаемой.

## Синхронизация и версия

Согласно `CLAUDE.md`: оба новых файла (`mybooksmate/page_scraper.py`,
`mybooksmate/book_selection_dialog.py`) и изменённый `main_window.py`
копируются в `release-Win/mybooksmate/` и
`release-Mac/MyBooksMate.app/Contents/Resources/mybooksmate/` в том же
изменении. Debug-версия в `mybooksmate/version.py` увеличивается в том же
изменении (и копируется в обе releaseе-папки). Обновить
`docs/CHANGELOG.md` и `README.md` по факту изменений.
