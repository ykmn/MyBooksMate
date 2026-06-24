import asyncio
import zipfile
import random
import os
import time
import re
import sys
import warnings
import json
import argparse
import shutil
import xml.etree.ElementTree as ET
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import httpx
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image

UA = {
    1: "Samsung/Galaxy_A51 Android/12 Bookmate/3.7.3",
    2: "Huawei/P40_Lite Android/11 Bookmate/3.7.3",
    3: "OnePlus/Nord_N10 Android/10 Bookmate/3.7.3"
    # 4: "Google/Pixel_4a Android/9 Bookmate/3.7.3",
    # 5: "Oppo/Reno_4 Android/8 Bookmate/3.7.3",
    # 6: "Xiaomi/Redmi_Note_9 Android/10 Bookmate/3.7.3",
    # 7: "Motorola/Moto_G_Power Android/10 Bookmate/3.7.3",
    # 8: "Sony/Xperia_10 Android/10 Bookmate/3.7.3",
    # 9: "LG/Velvet Android/10 Bookmate/3.7.3",
    # 10: "Realme/6_Pro Android/10 Bookmate/3.7.3",
}
HEADERS = {
    'app-user-agent': UA[random.randint(1, 3)],
    'mcc': '',
    'mnc': '',
    'imei': '',
    'subscription-country': '',
    'app-locale': '',
    'bookmate-version': '',
    'bookmate-websocket-version': '',
    'device-idfa': '',
    'onyx-preinstall': 'false',
    'auth-token': '',
    'accept-encoding': '',
    'user-agent': ''
}
BASE_URL = "https://api.bookmate.yandex.net/api/v5"
DOWNLOAD_BASE_DIR = "mybooks"
URLS = {
    "book": {
        "infoUrl": f"{BASE_URL}/books/{{uuid}}",
        "contentUrl": f"{BASE_URL}/books/{{uuid}}/content/v4"
    },
    "audiobook": {
        "infoUrl": f"{BASE_URL}/audiobooks/{{uuid}}",
        "contentUrl": f"{BASE_URL}/audiobooks/{{uuid}}/playlists.json"
    },
    "comicbook": {
        "infoUrl": f"{BASE_URL}/comicbooks/{{uuid}}",
        "contentUrl": f"{BASE_URL}/comicbooks/{{uuid}}/metadata.json"
    },
    "serial": {
        "infoUrl": f"{BASE_URL}/books/{{uuid}}",
        "contentUrl": f"{BASE_URL}/books/{{uuid}}/episodes"
    },
    "series": {
        "infoUrl": f"{BASE_URL}/series/{{uuid}}",
        "contentUrl": f"{BASE_URL}/series/{{uuid}}/parts"
    }
}


def get_auth_token():
    if os.path.isfile("token.txt"):
        with open("token.txt", encoding='utf-8') as file:
            return file.read()
    if HEADERS['auth-token']:
        return HEADERS['auth-token']
    auth_token = run_auth_webview()
    with open("token.txt", "w", encoding='utf-8') as file:
        file.write(auth_token)
    return auth_token


def run_auth_webview():
    import webview
    import urllib.parse

    def on_loaded(window):
        if "yx4483e97bab6e486a9822973109a14d05.oauth.yandex.ru" in urllib.parse.urlparse(window.get_current_url()).netloc:
            url = urllib.parse.urlparse(window.get_current_url())
            window.auth_token = urllib.parse.parse_qs(url.fragment)[
                'access_token'][0]
            window.destroy()

    window = webview.create_window(
        'Вход в аккаунт', 'https://oauth.yandex.ru/authorize?response_type=token&client_id=4483e97bab6e486a9822973109a14d05')
    window.events.loaded += on_loaded
    window.auth_token = None
    webview.start()
    return window.auth_token


def replace_forbidden_chars(filename):
    forbidden_chars = '\\/:*?"<>|'
    chars = re.escape(forbidden_chars)
    return re.sub(f'[{chars}]', '', filename)


async def download_file(url, file_path):
    is_download = False
    count = 0
    while not is_download:
        async with httpx.AsyncClient(http2=True, verify=False) as client:
            response = await client.get(url, headers=HEADERS, timeout=None)
            if response.status_code == 200:
                is_download = True
                with open(file_path, 'wb') as file:
                    file.write(response.content)
                print(f"File downloaded successfully to {file_path}")
            elif response.is_redirect:
                response = await client.get(response.next_request.url)
                if response.status_code == 200:
                    is_download = True
                    with open(file_path, 'wb') as file:
                        file.write(response.content)
                    print(f"File downloaded successfully to {file_path}")
            else:
                print(
                    f"Failed to download file. Status code: {response.status_code}")
                count += 1
                if count == 3:
                    print(
                        "Failed to download the file check if the id is correct or try again later")
                    sys.exit()
                time.sleep(5)


async def send_request(url):
    is_download = False
    count = 0
    while not is_download:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=HEADERS, timeout=None)
            if response.status_code == 200:
                is_download = True
                return response
            else:
                print(
                    f"Failed to send request. Status code: {response.status_code}")
                count += 1
                if count == 3:
                    print(
                        "Failed to download the file check if the id is correct or try again later")
                    sys.exit()
                time.sleep(5)


def create_pdf_from_images(images_folder, output_pdf):
    c = canvas.Canvas(output_pdf, pagesize=letter)
    width, height = letter

    images = filter(lambda file: file.endswith(".jpeg"), os.listdir(images_folder))

    for image in images:
        img_path = os.path.join(images_folder, image)
        with Image.open(img_path):
            c.drawImage(img_path, 0, 0, width, height)
            c.showPage()
        os.remove(img_path)
    c.save()
    print(f"File downloaded successfully to {output_pdf}")


OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}
CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}


def _find_opf_path(zip_file):
    container = zip_file.read("META-INF/container.xml")
    return ET.fromstring(container).find(".//c:rootfile", CONTAINER_NS).get("full-path")


def _resolve_href(base_dir, href):
    return f"{base_dir}/{href}" if base_dir else href


def _find_epub_image_items(zip_file):
    """Returns (cover_href_or_None, list_of_all_image_hrefs) parsed from the OPF."""
    opf_path = _find_opf_path(zip_file)
    opf_root = ET.fromstring(zip_file.read(opf_path))
    base_dir = os.path.dirname(opf_path)

    cover_id = None
    metadata = opf_root.find("opf:metadata", OPF_NS)
    if metadata is not None:
        for meta in metadata.findall("opf:meta", OPF_NS):
            if meta.get("name") == "cover":
                cover_id = meta.get("content")
                break

    manifest = opf_root.find("opf:manifest", OPF_NS)
    if manifest is None:
        return None, []

    cover_href = None
    image_hrefs = []
    for item in manifest.findall("opf:item", OPF_NS):
        media_type = item.get("media-type") or ""
        properties = item.get("properties") or ""
        href = _resolve_href(base_dir, item.get("href"))
        is_cover = item.get("id") == cover_id or "cover-image" in properties
        if is_cover:
            cover_href = href
        if media_type.startswith("image/"):
            image_hrefs.append(href)
    return cover_href, image_hrefs


MIN_VALID_COVER_SIZE = 1024  # bytes


def fix_epub_cover(epub_path, cover_image_path):
    """Bookmate's exported epub sometimes references a cover image that's
    either missing from the archive entirely (causes ebooklib warnings like
    "There is no item named '...jpeg' in the archive") or present but as a
    tiny placeholder (observed: a single-byte file instead of the real
    image) — both cases leave the book without a cover everywhere the epub
    is opened. Patch the already-downloaded cover jpeg into the archive at
    the path the manifest expects, replacing it if it's there but broken.

    The book's cover isn't always explicitly marked in the OPF (no
    meta name="cover" / properties="cover-image") — when that's the case,
    fall back to whichever referenced image is actually missing/broken in
    the archive (Bookmate's text-only exports typically reference exactly
    one image: the cover)."""
    if not os.path.isfile(cover_image_path):
        return
    try:
        with zipfile.ZipFile(epub_path, "r") as zip_file:
            cover_href, image_hrefs = _find_epub_image_items(zip_file)
            sizes = {info.filename: info.file_size for info in zip_file.infolist()}
            contents = {info.filename: zip_file.read(info.filename) for info in zip_file.infolist()}

        def is_broken(href):
            return href not in sizes or sizes[href] < MIN_VALID_COVER_SIZE

        broken_images = [href for href in image_hrefs if is_broken(href)]
        if cover_href and is_broken(cover_href):
            target_href = cover_href
        elif len(broken_images) == 1:
            target_href = broken_images[0]
        elif broken_images:
            target_href = broken_images[0]
            print(f"В EPUB несколько отсутствующих/повреждённых изображений {broken_images}, "
                  f"обложка восстановлена в {target_href}")
        else:
            print("В EPUB обложка уже присутствует и выглядит исправной")
            return

        with open(cover_image_path, "rb") as image_file:
            contents[target_href] = image_file.read()

        with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if "mimetype" in contents:
                zip_file.writestr("mimetype", contents.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
            for name, data in contents.items():
                zip_file.writestr(name, data)
        print(f"Восстановлена обложка в EPUB: {target_href}")
    except Exception as exc:  # noqa: BLE001
        print(f"Не удалось проверить/восстановить обложку EPUB: {exc}")


BOOKS_PAGE_URL = "https://books.yandex.ru/books/{uuid}"
DC_NS = "http://purl.org/dc/elements/1.1/"


def fetch_page_metadata(uuid):
    """Scrapes tags/publisher/year metadata from the public book page on
    books.yandex.ru — this isn't exposed via the Bookmate content API."""
    metadata = {"tags": []}
    try:
        response = httpx.get(
            BOOKS_PAGE_URL.format(uuid=uuid),
            headers={"user-agent": "Mozilla/5.0"},
            timeout=20, follow_redirects=True, verify=False,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"Не удалось получить метаданные со страницы книги: {exc}")
        return metadata

    soup = BeautifulSoup(response.text, "html.parser")

    for item in soup.find_all(attrs={"data-test-id": "CONTENT_INFO_ITEM"}):
        label_el = item.find(attrs={"class": re.compile("ContentInfo_label")})
        value_el = item.find(attrs={"class": re.compile("ContentInfo_value")})
        if not label_el or not value_el:
            continue
        label = label_el.get_text(strip=True).rstrip(":").lower()
        value = value_el.get_text(strip=True)
        if "издательств" in label:
            metadata["publisher"] = value
        elif "год выхода" in label:
            metadata["year"] = value

    topics_container = soup.find(attrs={"data-test-id": "CONTENT_TOPICS"})
    if topics_container:
        for tag_el in topics_container.find_all(attrs={"data-test-id": "CONTENT_TOPICS_SLUG"}):
            text = tag_el.get_text(strip=True)
            if text:
                metadata["tags"].append(text)

    return metadata


def embed_epub_metadata(epub_path, metadata):
    """Adds dc:subject (tags), dc:publisher and dc:date entries to the epub's
    OPF metadata, scraped from the book's page (see fetch_page_metadata)."""
    if not metadata or not (metadata.get("tags") or metadata.get("publisher") or metadata.get("year")):
        return
    try:
        with zipfile.ZipFile(epub_path, "r") as zip_file:
            opf_path = _find_opf_path(zip_file)
            contents = {info.filename: zip_file.read(info.filename) for info in zip_file.infolist()}

        ET.register_namespace("", OPF_NS["opf"])
        ET.register_namespace("dc", DC_NS)
        root = ET.fromstring(contents[opf_path])
        metadata_el = root.find("opf:metadata", OPF_NS)
        if metadata_el is None:
            return

        for tag in metadata.get("tags", []):
            ET.SubElement(metadata_el, f"{{{DC_NS}}}subject").text = tag
        if metadata.get("publisher"):
            ET.SubElement(metadata_el, f"{{{DC_NS}}}publisher").text = metadata["publisher"]
        if metadata.get("year"):
            ET.SubElement(metadata_el, f"{{{DC_NS}}}date").text = metadata["year"]

        contents[opf_path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if "mimetype" in contents:
                zip_file.writestr("mimetype", contents.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
            for name, data in contents.items():
                zip_file.writestr(name, data)
        print(f"В EPUB добавлены метаданные: теги={metadata.get('tags')}, "
              f"издательство={metadata.get('publisher')}, год={metadata.get('year')}")
    except Exception as exc:  # noqa: BLE001
        print(f"Не удалось добавить метаданные в EPUB: {exc}")


def epub_to_fb2(epub_path, fb2_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        book = epub.read_epub(epub_path)

    fb2_content = '<?xml version="1.0" encoding="UTF-8"?>\n<fb2 xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">\n<body>'
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            content = item.get_content()
            soup = BeautifulSoup(content, 'html.parser')
            text_content = soup.get_text()
            fb2_content += f'<p>{text_content}</p>'

    fb2_content += '</body>\n</fb2>'

    with open(fb2_path, 'w', encoding='utf-8') as fb2_file:
        fb2_file.write(fb2_content)

    print(f"fb2 file save to {fb2_path}")


NEEDS_DIR_TYPES = {'audiobook', 'comicbook', 'series'}


def extract_authors(resource_info):
    authors = resource_info.get('authors')
    if isinstance(authors, list):
        names = []
        for author in authors:
            if isinstance(author, dict) and author.get('name'):
                names.append(author['name'])
            elif isinstance(author, str) and author:
                names.append(author)
        return ", ".join(names)
    if isinstance(authors, str):
        return authors
    return ""


def get_resource_info(resource_type, uuid, series='', force_dir=False):
    info_url = URLS[resource_type]['infoUrl'].format(uuid=uuid)
    info = asyncio.run(send_request(info_url)).json()
    if info:
        resource_info = info[resource_type]
        picture_url = resource_info["cover"]["large"]
        title = replace_forbidden_chars(resource_info["title"])
        authors = extract_authors(resource_info)
        name = replace_forbidden_chars(f"{authors} - {title}" if authors else title)
        if resource_type in NEEDS_DIR_TYPES or series or force_dir:
            download_dir = f"{DOWNLOAD_BASE_DIR}/{series}{name}/"
            os.makedirs(download_dir, exist_ok=True)
            path = f'{download_dir}{name}'
        else:
            os.makedirs(DOWNLOAD_BASE_DIR, exist_ok=True)
            path = f'{DOWNLOAD_BASE_DIR}/{name}'
        asyncio.run(download_file(picture_url, f'{path}.jpeg'))
        with open(f"{path}.json", 'w', encoding='utf-8') as file:
            file.write(json.dumps(info, ensure_ascii=False))
        print(f"File downloaded successfully to {path}.json")
    return path


def get_resource_json(resource_type, uuid):
    url = URLS[resource_type]['contentUrl'].format(uuid=uuid)
    return asyncio.run(send_request(url)).json()


EXISTING_FILE_EXT = {'book': '.epub', 'comicbook': '.pdf'}


def find_existing_file(resource_type, uuid):
    """For resource types that produce a single final file (book/comicbook),
    fetches the resource's metadata to compute its expected path and returns
    that path if the file already exists on disk, else None. Used by the GUI
    to ask the user whether to re-download or skip before starting work."""
    ext = EXISTING_FILE_EXT.get(resource_type)
    if not ext:
        return None
    path = get_resource_info(resource_type, uuid)
    file_path = f'{path}{ext}'
    return file_path if os.path.isfile(file_path) else None


def download_book(uuid, series='', serial_path=None, force=False, convert_to_fb2=False):
    path = serial_path if serial_path else get_resource_info(
        'book', uuid, series)
    epub_path = f'{path}.epub'
    if os.path.isfile(epub_path) and not force:
        print(f"Книга уже скачана, повторное скачивание не требуется: {epub_path}")
        fix_epub_cover(epub_path, f'{path}.jpeg')
        return epub_path, True
    asyncio.run(download_file(
        URLS['book']['contentUrl'].format(uuid=uuid), epub_path))
    fix_epub_cover(epub_path, f'{path}.jpeg')
    embed_epub_metadata(epub_path, fetch_page_metadata(uuid))
    # embed_epub_metadata rewrites the whole archive — re-check the cover
    # survived the rewrite and patch it back in if it didn't.
    fix_epub_cover(epub_path, f'{path}.jpeg')
    if convert_to_fb2:
        epub_to_fb2(epub_path, f"{path}.fb2")
    return epub_path, False


def download_audiobook(uuid, series='', max_bitrate=False):
    path = get_resource_info('audiobook', uuid, series)
    resp = get_resource_json('audiobook', uuid)
    already_downloaded = False
    if resp:
        bitrate = 'max_bit_rate' if max_bitrate else 'min_bit_rate'
        json_data = resp['tracks']
        files = os.listdir(os.path.dirname(path))
        already_downloaded = True
        for track in json_data:
            name = f'Глава_{track["number"]+1}.m4a'
            if name not in files:
                already_downloaded = False
                download_url = track['offline'][bitrate]['url'].replace(".m3u8", ".m4a")
                asyncio.run(download_file(
                    download_url, f'{os.path.dirname(path)}/{name}'))
    return os.path.dirname(path), already_downloaded


def download_comicbook(uuid, series='', force=False):
    path = get_resource_info('comicbook', uuid, series)
    pdf_path = f'{path}.pdf'
    if os.path.isfile(pdf_path) and not force:
        print(f"Комикс уже скачан, повторное скачивание не требуется: {pdf_path}")
        return pdf_path, True
    resp = get_resource_json('comicbook', uuid)
    if resp:
        download_url = resp["uris"]["zip"]
        asyncio.run(download_file(download_url, f'{path}.cbr'))
        with zipfile.ZipFile(f'{path}.cbr', 'r') as zip_ref:
            zip_ref.extractall(os.path.dirname(path))
        shutil.rmtree(os.path.dirname(path)+"/preview",
                      ignore_errors=False, onerror=None)
        create_pdf_from_images(os.path.dirname(path), pdf_path)
    return pdf_path, False


def download_serial(uuid, force=False, convert_to_fb2=False):
    path = get_resource_info('book', uuid, force_dir=True)
    resp = get_resource_json('serial', uuid)
    already_downloaded = False
    if resp:
        already_downloaded = True
        for episode_index, episode in enumerate(resp["episodes"]):
            name = f"{episode_index+1}. {episode['title']}"
            download_dir = f'{os.path.dirname(path)}/{name}'
            os.makedirs(download_dir, exist_ok=True)
            _, episode_already_downloaded = download_book(
                episode['uuid'], serial_path=f'{download_dir}/{name}',
                force=force, convert_to_fb2=convert_to_fb2)
            already_downloaded = already_downloaded and episode_already_downloaded
    return os.path.dirname(path), already_downloaded


def download_series(uuid):
    path = get_resource_info('series', uuid)
    resp = get_resource_json('series', uuid)
    name = os.path.basename(path)
    print(name)
    for part_index, part in enumerate(resp['parts']):
        print(part['resource_type'], part['resource']['uuid'])
        func = FUNCTION_MAP[part['resource_type']]
        func(part['resource']['uuid'], f"{name}/{part_index+1}. ")
    return os.path.dirname(path), False


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("command", choices=FUNCTION_MAP.keys())
    argparser.add_argument("uuid")
    argparser.add_argument("--max_bitrate", action='store_false')
    args = argparser.parse_args()

    HEADERS['auth-token'] = get_auth_token()

    func = FUNCTION_MAP[args.command]
    if args.command == 'audiobook':
        func(args.uuid, max_bitrate=args.max_bitrate)
    else:
        func(args.uuid)


FUNCTION_MAP = {
    'book': download_book,
    'audiobook': download_audiobook,
    'comicbook': download_comicbook,
    'serial': download_serial,
    'series': download_series
}

if __name__ == "__main__":
    main()
