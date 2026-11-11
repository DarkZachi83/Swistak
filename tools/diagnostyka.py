# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bezpieczny test środowiska po spakowaniu PyInstaller.

Nie otwiera SQLite, nie tworzy bazy i nie łączy się z Ollamą.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def self_test() -> int:
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtGui import QPixmap
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtWidgets import QApplication
        import pdfplumber  # noqa: F401
        import pypdfium2  # noqa: F401
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401

        from i18n import set_language, t
        from gui.okno_o_programie import ILLUSTRATIONS
        from wersja import DISPLAY_VERSION

        app = QApplication.instance() or QApplication(["Swistak", "--self-test"])
        assert app is not None
        assert QPdfDocument is not None
        for language in ("pl", "en"):
            set_language(language)
            if not t("about.title"):
                raise RuntimeError("Brak tłumaczenia: " + language)
        poster = next((path for path in ILLUSTRATIONS if path.is_file()), None)
        if poster is None or QPixmap(str(poster)).isNull():
            raise RuntimeError("Nie znaleziono poprawnej ilustracji JPEG")
        schemat = Path(__file__).resolve().parents[1] / "baza" / "schemat"
        names = ("001_start.sql", "002_numer_konta.sql")
        if not all((schemat / name).is_file() for name in names):
            raise RuntimeError("Nie znaleziono historycznych migracji SQL")
        print("Świstak " + DISPLAY_VERSION + " — test binarny OK")
        print("Qt:", app.platformName(), "| JPEG:", poster.name, "| migracje: 001, 002")
        print("Dane użytkownika nie były otwierane.")
        return 0
    except Exception as exc:
        print("Świstak — błąd diagnostyki:", exc, file=sys.stderr)
        return 1
