import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .version import __version__


def _bundle_dir():
    # Icons are a static asset shipped alongside the mybooksmate package
    # (next to it on Windows, inside Contents/Resources on macOS) — unlike
    # config.py's _app_dir(), this never points at the user's writable data
    # directory, so it ignores MYBOOKSMATE_APP_DIR on purpose.
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("MyBooksMate")
    app.setOrganizationName("MyBooksMate")
    app.setApplicationVersion(__version__)

    for icon_name in ("favicon.ico", "favicon.icns", "favicon_1024.png"):
        icon_path = os.path.join(_bundle_dir(), icon_name)
        if os.path.isfile(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
