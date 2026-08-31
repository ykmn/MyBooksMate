from PySide6.QtCore import QObject, QThread, Signal

from . import calibre, downloader


class DownloadWorker(QObject):
    finished = Signal(str, bool, str)
    failed = Signal(str)

    def __init__(self, resource_type, uuid, download_folder, auth_token, max_bitrate, add_to_calibre, calibre_path, force=False, convert_to_fb2=False):
        super().__init__()
        self.resource_type = resource_type
        self.uuid = uuid
        self.download_folder = download_folder
        self.auth_token = auth_token
        self.max_bitrate = max_bitrate
        self.add_to_calibre = add_to_calibre
        self.calibre_path = calibre_path
        self.force = force
        self.convert_to_fb2 = convert_to_fb2

    def run(self):
        try:
            path, already_downloaded = downloader.download(
                self.resource_type, self.uuid, self.download_folder,
                self.auth_token, self.max_bitrate, self.force, self.convert_to_fb2,
            )
            calibre_message = ""
            if self.add_to_calibre and path:
                calibre_message = calibre.add_to_calibre(self.calibre_path, path)
            self.finished.emit(path or "", bool(already_downloaded), calibre_message)
        except SystemExit:
            # RUBookmatedownloader.py's retry loop calls a bare sys.exit() after 3 failed
            # attempts, which raises SystemExit — this isn't an Exception subclass, so it
            # must be caught separately or it crashes the whole app instead of just failing
            # this one download.
            self.failed.emit("Не удалось скачать файл после нескольких попыток (ошибка сервера или сети). Проверьте ID книги или повторите позже.")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


def start_download(parent, resource_type, uuid, download_folder, auth_token, max_bitrate, add_to_calibre, calibre_path, on_finished, on_failed, force=False, convert_to_fb2=False):
    thread = QThread(parent)
    worker = DownloadWorker(
        resource_type, uuid, download_folder, auth_token,
        max_bitrate, add_to_calibre, calibre_path, force, convert_to_fb2,
    )
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(thread.deleteLater)
    # keep references alive on the parent so they are not garbage collected mid-run
    parent._download_thread = thread
    parent._download_worker = worker
    thread.start()
