import json
import os
import platform
import re
import subprocess

IS_WINDOWS = platform.system() == "Windows"


def _exe_name(base_name):
    return f"{base_name}.exe" if IS_WINDOWS else base_name


class CalibreError(Exception):
    pass


def _resolve_exe(calibre_path, base_name):
    exe_name = _exe_name(base_name)
    if os.path.isdir(calibre_path):
        return os.path.join(calibre_path, exe_name)
    basename = os.path.basename(calibre_path).lower()
    if basename in (_exe_name("calibre").lower(), _exe_name("calibredb").lower(), "calibre", "calibredb"):
        return os.path.join(os.path.dirname(calibre_path), exe_name)
    return calibre_path


def _is_calibre_running():
    if IS_WINDOWS:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq calibre.exe"],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
        )
        return "calibre.exe" in result.stdout.lower()
    result = subprocess.run(["pgrep", "-x", "calibre"], capture_output=True, text=True)
    return result.returncode == 0


def _read_authors_from_json(file_path):
    """Authors aren't embedded in the epub by ebooklib's writer, but the raw
    Bookmate API response saved alongside the book (<name>.json) has them."""
    json_path = os.path.splitext(file_path)[0] + ".json"
    if not os.path.isfile(json_path):
        return []
    try:
        with open(json_path, encoding="utf-8") as file:
            data = json.load(file)
    except Exception:  # noqa: BLE001
        return []
    for resource in data.values():
        if isinstance(resource, dict) and resource.get("authors"):
            names = []
            for author in resource["authors"]:
                if isinstance(author, dict) and author.get("name"):
                    names.append(author["name"])
                elif isinstance(author, str) and author:
                    names.append(author)
            return names
    return []


def _author_sort_name(full_name):
    """'Евгений Добренко' -> 'Добренко, Евгений' (last whitespace-separated
    word is treated as the surname; this also keeps hyphenated surnames like
    'Джонссон-Скрадоль' intact since there's no space inside them)."""
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return full_name.strip()
    surname = parts[-1]
    given_names = " ".join(parts[:-1])
    return f"{surname}, {given_names}"


def format_author_sort(names):
    return " & ".join(_author_sort_name(name) for name in names if name)


def add_to_calibre(calibre_path, file_path):
    """Adds a single book file to the default Calibre library.

    calibre_path is expected to point to Calibre's installation folder or to
    calibre.exe / calibredb.exe directly. Returns a human-readable status message.
    """
    if not calibre_path:
        raise CalibreError("Путь к Calibre не задан в настройках")
    if not os.path.isfile(file_path):
        raise CalibreError(f"Файл для добавления не найден: {file_path}")

    if _is_calibre_running():
        # calibredb locks the library file directly, which conflicts with a
        # running GUI instance and silently fails to add the book. Instead,
        # hand the file to the running instance the same way Windows does
        # when double-clicking a book with Calibre as the default app — it
        # gets picked up and added to the currently open library. Setting an
        # explicit author_sort isn't possible in this path since we don't get
        # the new book's id back from a fire-and-forget IPC call.
        calibre_exe = _resolve_exe(calibre_path, "calibre")
        if not os.path.isfile(calibre_exe):
            raise CalibreError(f"Не найден исполняемый файл calibre: {calibre_exe}")
        subprocess.run([calibre_exe, file_path], check=False)
        return "Книга передана в запущенный Calibre"

    calibredb = _resolve_exe(calibre_path, "calibredb")
    if not os.path.isfile(calibredb):
        raise CalibreError(f"Не найден исполняемый файл calibredb: {calibredb}")

    command = [calibredb, "add", file_path]
    cover_path = os.path.splitext(file_path)[0] + ".jpeg"
    if os.path.isfile(cover_path):
        command.append(f"--cover={cover_path}")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if result.returncode != 0:
        raise CalibreError(result.stderr or "calibredb add завершился с ошибкой")

    author_sort = format_author_sort(_read_authors_from_json(file_path))
    book_id_match = re.search(r"Added book ids?:\s*(\d+)", result.stdout)
    if author_sort and book_id_match:
        subprocess.run(
            [calibredb, "set_metadata", book_id_match.group(1), "--field", f"author_sort:{author_sort}"],
            capture_output=True, text=True, encoding="utf-8", errors="ignore",
        )

    return "Книга добавлена в Calibre"
