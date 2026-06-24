import configparser
import os
import sys

CONFIG_FILE_NAME = "config.ini"


def _app_dir():
    override = os.environ.get("MYBOOKSMATE_APP_DIR")
    if override:
        return override
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AppConfig:
    """Stores app settings in config.ini next to the executable/script."""

    def __init__(self):
        self.path = os.path.join(_app_dir(), CONFIG_FILE_NAME)
        self.parser = configparser.ConfigParser()
        self._load()

    def _load(self):
        self.parser.read(self.path, encoding="utf-8")
        if "Settings" not in self.parser:
            self.parser["Settings"] = {}
        defaults = {
            "download_folder": os.path.join(_app_dir(), "mybooks"),
            "calibre_path": "",
            "max_bitrate": "false",
            "convert_to_fb2": "false",
        }
        for key, value in defaults.items():
            if key not in self.parser["Settings"]:
                self.parser["Settings"][key] = value
        self.save()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as file:
            self.parser.write(file)

    @property
    def download_folder(self):
        return self.parser["Settings"]["download_folder"]

    @download_folder.setter
    def download_folder(self, value):
        self.parser["Settings"]["download_folder"] = value
        self.save()

    @property
    def calibre_path(self):
        return self.parser["Settings"]["calibre_path"]

    @calibre_path.setter
    def calibre_path(self, value):
        self.parser["Settings"]["calibre_path"] = value
        self.save()

    @property
    def max_bitrate(self):
        return self.parser["Settings"].getboolean("max_bitrate", fallback=False)

    @max_bitrate.setter
    def max_bitrate(self, value):
        self.parser["Settings"]["max_bitrate"] = "true" if value else "false"
        self.save()

    @property
    def convert_to_fb2(self):
        return self.parser["Settings"].getboolean("convert_to_fb2", fallback=False)

    @convert_to_fb2.setter
    def convert_to_fb2(self, value):
        self.parser["Settings"]["convert_to_fb2"] = "true" if value else "false"
        self.save()

    @property
    def splitter_sizes(self):
        raw = self.parser["Settings"].get("splitter_sizes", "")
        if not raw:
            return None
        try:
            return [int(part) for part in raw.split(",")]
        except ValueError:
            return None

    @splitter_sizes.setter
    def splitter_sizes(self, sizes):
        self.parser["Settings"]["splitter_sizes"] = ",".join(str(size) for size in sizes)
        self.save()

    @property
    def window_geometry(self):
        raw = self.parser["Settings"].get("window_geometry", "")
        if not raw:
            return None
        try:
            return bytes.fromhex(raw)
        except ValueError:
            return None

    @window_geometry.setter
    def window_geometry(self, geometry_bytes):
        self.parser["Settings"]["window_geometry"] = bytes(geometry_bytes).hex()
        self.save()
