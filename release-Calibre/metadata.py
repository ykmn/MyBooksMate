"""
EPUB cover/metadata fixups, ported from mybooksmate/RUBookmatedownloader.py
(the desktop app) to stdlib-only (zipfile, ElementTree, re) — no BeautifulSoup
or PIL, so the plugin doesn't need to vendor anything into the zip Calibre
loads. See that file for the original implementation/history of these fixes.
"""

import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

BOOKS_PAGE_URL = "https://books.yandex.ru/books/{uuid}"
OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}
CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
DC_NS = "http://purl.org/dc/elements/1.1/"
MIN_VALID_COVER_SIZE = 1024  # bytes

# Each item's inner HTML, e.g.:
#   <span class="ContentInfo_label...">Издательство<!-- -->:</span>
#   <span class="ContentInfo_value..."><span><a ...>Name</a></span></span>
# The value is plain text for some fields (year) but wrapped in nested
# <span>/<a> for others (publisher) — so the value is extracted as the raw
# HTML up to the *last* </span> in the item, then stripped of any tags,
# rather than assuming either shape.
_ITEM_RE = re.compile(r'data-test-id="CONTENT_INFO_ITEM">(.*?)</div>', re.S)
_LABEL_RE = re.compile(r'class="ContentInfo_label[^"]*">([^<]+?)<!--\s*-->:</span>', re.S)
_VALUE_RE = re.compile(r'class="ContentInfo_value[^"]*">(.*)</span>', re.S)
_TAG_RE = re.compile(r'<[^>]+>')
_TOPIC_RE = re.compile(
    r'data-test-id="CONTENT_TOPICS_SLUG"[^>]*>\s*<span[^>]*>([^<]+)</span>'
)


def fetch_page_metadata(uuid, timeout=20):
    """Scrapes tags/publisher/year metadata from the public book page on
    books.yandex.ru — this isn't exposed via the Bookmate content API."""
    metadata = {"tags": []}
    try:
        request = urllib.request.Request(
            BOOKS_PAGE_URL.format(uuid=uuid), headers={"user-agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return metadata

    for item_html in _ITEM_RE.findall(html):
        label_match = _LABEL_RE.search(item_html)
        value_match = _VALUE_RE.search(item_html)
        if not label_match or not value_match:
            continue
        label = label_match.group(1).strip().lower()
        value = _TAG_RE.sub('', value_match.group(1)).strip()
        if not value:
            continue
        if "издательств" in label:
            metadata["publisher"] = value
        elif "год выхода" in label:
            metadata["year"] = value

    metadata["tags"] = [tag.strip() for tag in _TOPIC_RE.findall(html) if tag.strip()]
    return metadata


def _find_opf_path(zip_file):
    container = zip_file.read("META-INF/container.xml")
    return ET.fromstring(container).find(".//c:rootfile", CONTAINER_NS).get("full-path")


def _resolve_href(base_dir, href):
    return f"{base_dir}/{href}" if base_dir else href


def _find_epub_image_items(zip_file):
    """Returns (cover_href_or_None, list_of_all_image_hrefs) parsed from the OPF."""
    opf_path = _find_opf_path(zip_file)
    opf_root = ET.fromstring(zip_file.read(opf_path))
    base_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""

    cover_id = None
    metadata_el = opf_root.find("opf:metadata", OPF_NS)
    if metadata_el is not None:
        for meta in metadata_el.findall("opf:meta", OPF_NS):
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


def fix_epub_cover(epub_path, cover_bytes):
    """Bookmate's exported epub sometimes references a cover image that's
    either missing from the archive entirely or present but as a tiny
    placeholder, leaving the book without a cover everywhere the epub is
    opened. Patch the given cover image bytes into the archive at the path
    the manifest expects, replacing it if it's there but broken."""
    if not cover_bytes:
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
        elif broken_images:
            target_href = broken_images[0]
        else:
            return

        contents[target_href] = cover_bytes

        with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if "mimetype" in contents:
                zip_file.writestr("mimetype", contents.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
            for name, data in contents.items():
                zip_file.writestr(name, data)
    except Exception:
        pass


def prepare_epub(epub_path, uuid, cover_bytes):
    fix_epub_cover(epub_path, cover_bytes)
    page_metadata = fetch_page_metadata(uuid)
    embed_epub_metadata(epub_path, page_metadata)
    fix_epub_cover(epub_path, cover_bytes)


def embed_epub_metadata(epub_path, metadata):
    """Adds dc:subject (tags), dc:publisher and dc:date entries to the
    epub's OPF metadata, scraped from the book's page (see
    fetch_page_metadata)."""
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
    except Exception:
        pass
