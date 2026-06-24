import platform

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

IS_WINDOWS = platform.system() == "Windows"
CALIBRE_LABEL = "Путь к calibre.exe / calibredb.exe:" if IS_WINDOWS else "Путь к calibre / calibredb:"
CALIBRE_FILTER = "Исполняемые файлы (*.exe)" if IS_WINDOWS else "Все файлы (*)"


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(640)

        self.download_folder_edit = QLineEdit(config.download_folder)
        self.calibre_path_edit = QLineEdit(config.calibre_path)
        self.max_bitrate_checkbox = QCheckBox("Максимальный битрейт для аудиокниг по умолчанию")
        self.max_bitrate_checkbox.setChecked(config.max_bitrate)
        self.convert_to_fb2_checkbox = QCheckBox("Конвертировать книги в fb2")
        self.convert_to_fb2_checkbox.setChecked(config.convert_to_fb2)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Папка для скачивания книг:"))
        layout.addLayout(self._row(self.download_folder_edit, self._browse_folder))
        layout.addWidget(QLabel(CALIBRE_LABEL))
        layout.addLayout(self._row(self.calibre_path_edit, self._browse_calibre))
        layout.addWidget(self.max_bitrate_checkbox)
        layout.addWidget(self.convert_to_fb2_checkbox)

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self._save)
        layout.addWidget(save_button)

    def _row(self, edit, slot):
        button = QPushButton("Обзор...")
        button.clicked.connect(slot)
        row = QHBoxLayout()
        row.addWidget(edit)
        row.addWidget(button)
        return row

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для скачивания", self.download_folder_edit.text())
        if folder:
            self.download_folder_edit.setText(folder)

    def _browse_calibre(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите calibre или calibredb", self.calibre_path_edit.text(), CALIBRE_FILTER)
        if path:
            self.calibre_path_edit.setText(path)

    def _save(self):
        self.config.download_folder = self.download_folder_edit.text()
        self.config.calibre_path = self.calibre_path_edit.text()
        self.config.max_bitrate = self.max_bitrate_checkbox.isChecked()
        self.config.convert_to_fb2 = self.convert_to_fb2_checkbox.isChecked()
        self.accept()
