from . import RUBookmatedownloader as core

# resource_type -> can a downloaded file be added to Calibre as an ebook
CALIBRE_COMPATIBLE = {"book", "comicbook", "serial"}


def download(resource_type, uuid, download_folder, auth_token, max_bitrate=False, force=False, convert_to_fb2=False):
    """Downloads a resource using the existing core script and returns the result path."""
    core.DOWNLOAD_BASE_DIR = download_folder
    core.HEADERS["auth-token"] = auth_token

    func = core.FUNCTION_MAP[resource_type]
    if resource_type == "audiobook":
        return func(uuid, max_bitrate=max_bitrate)
    if resource_type == "book":
        return func(uuid, force=force, convert_to_fb2=convert_to_fb2)
    if resource_type == "comicbook":
        return func(uuid, force=force)
    if resource_type == "serial":
        return func(uuid, force=force, convert_to_fb2=convert_to_fb2)
    return func(uuid)


def find_existing_file(resource_type, uuid, download_folder, auth_token):
    """Checks (without downloading content) whether the book/comicbook for this
    uuid was already downloaded. Returns the existing file path or None."""
    core.DOWNLOAD_BASE_DIR = download_folder
    core.HEADERS["auth-token"] = auth_token
    return core.find_existing_file(resource_type, uuid)
