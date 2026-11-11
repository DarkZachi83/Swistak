# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Graficzne okno O programie — odrębne od bazy i ustawień rachunków.

Zdjęcie w pełnej rozdzielczości JPEG jest ładowane z lokalnych zasobów.
Teksty i przyciski są PRAWDZIWYMI widgetami Qt,
a nie napisami wypalonymi w obrazku.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from i18n import t
from wersja import DISPLAY_VERSION


GITHUB = "https://github.com/DarkZachi83/Swistak"
ROOT = Path(__file__).resolve().parents[1]
ILLUSTRATIONS = (
    ROOT / "assets" / "about" / "swistak-o-programie.jpeg",
    ROOT / "assets" / "branding" / "swistak-banner.jpeg",
)


class OknoOProgramie(QDialog):
    """Podobny układ do okna AI Bobra, bez kopiowania jego kodu."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("oknoOProgramie")
        self.setWindowTitle(t("about.title"))
        self.setModal(True)
        self.setMinimumWidth(440)
        self.resize(660, 715)
        self.setStyleSheet("""
            QDialog#oknoOProgramie { background: #212529; color: #f1f3f5; }
            QDialog#oknoOProgramie QLabel { color: #f1f3f5; }
            QDialog#oknoOProgramie QScrollArea { border: none; background: #212529; }
            QDialog#oknoOProgramie QScrollArea > QWidget > QWidget {
                background: #212529;
            }
            QDialog#oknoOProgramie QPushButton {
                background: #333a40; color: #f8f9fa;
                border: 1px solid #58636c; border-radius: 5px;
                padding: 8px 16px; font-weight: 600;
            }
            QDialog#oknoOProgramie QPushButton:hover {
                background: #46515a; border-color: #75bacb;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(10)

        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(area, 1)
        content = QWidget()
        area.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        self.hero = QLabel()
        self.hero.setObjectName("aboutHero")
        self.hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self._find_illustration()
        if pixmap is None:
            self.hero.setText(t("about.image_missing"))
            self.hero.setMinimumHeight(110)
        else:
            max_width = 605
            screen = self.screen()
            if screen:
                max_width = min(max_width, max(340, screen.availableGeometry().width() - 105))
            ratio = max(1.0, self.devicePixelRatioF())
            scaled = self._scaled_for_hidpi(pixmap, max_width, 320, ratio)
            self.hero.setPixmap(scaled)
            self.hero.setFixedHeight(round(scaled.height() / ratio))
        content_layout.addWidget(self.hero)

        self.title = QLabel("Świstak")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("font-size: 27px; font-weight: 750; margin-top: 7px;")
        content_layout.addWidget(self.title)

        self.subtitle = self._centered(t("about.subtitle", version=DISPLAY_VERSION))
        self.subtitle.setStyleSheet("font-size: 15px; color: #dce2e6;")
        content_layout.addWidget(self.subtitle)

        self.features = self._centered("PDF · OCR · SQLite · Ollama")
        self.features.setStyleSheet("color: #aab8bf; font-size: 13px;")
        content_layout.addWidget(self.features)

        self.tagline = self._centered(t("about.tagline"))
        self.tagline.setStyleSheet("font-size: 13px; margin-top: 6px;")
        content_layout.addWidget(self.tagline)

        self.author = self._centered(t("about.author"))
        self.author.setStyleSheet("font-size: 12px; margin-top: 5px;")
        content_layout.addWidget(self.author)

        self.license = self._centered(t("about.license"))
        self.license.setStyleSheet("font-size: 12px; color: #bec6cc;")
        content_layout.addWidget(self.license)

        self.privacy = self._centered(t("about.privacy"))
        self.privacy.setStyleSheet("color: #adb9c2; font-size: 11px;")
        content_layout.addWidget(self.privacy)

        self.star_hint = self._centered(t("about.star_hint"))
        self.star_hint.setStyleSheet("margin-top: 4px; font-size: 12px;")
        content_layout.addWidget(self.star_hint)

        actions = QHBoxLayout()
        actions.setSpacing(9)
        actions.addStretch()
        self.star_button = QPushButton(t("about.star_button"))
        self.star_button.setObjectName("aboutStarButton")
        self.star_button.clicked.connect(self._open_github)
        actions.addWidget(self.star_button)
        self.close_button = QPushButton(t("about.close"))
        self.close_button.setObjectName("aboutCloseButton")
        self.close_button.clicked.connect(self.accept)
        actions.addWidget(self.close_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.close_button.setDefault(True)

    @staticmethod
    def _centered(value: str) -> QLabel:
        label = QLabel(value)
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _scaled_for_hidpi(pixmap: QPixmap, width: int, height: int,
                          ratio: float) -> QPixmap:
        """Skalowanie do fizycznych pikseli ekranu, bez rozmywania na HiDPI."""
        ratio = max(1.0, ratio)
        scaled = pixmap.scaled(
            round(width * ratio), round(height * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(ratio)
        return scaled

    @staticmethod
    def _find_illustration() -> QPixmap | None:
        for path in ILLUSTRATIONS:
            if path.is_file():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    return pix
        return None

    def _open_github(self) -> None:
        # Wywoływane dopiero po świadomym kliknięciu przez użytkownika.
        QDesktopServices.openUrl(QUrl(GITHUB))
