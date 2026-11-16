# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Regresja kolejności zamykania Qt i zasobów używanych przez OCR."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class TestZamykanieAplikacji(unittest.TestCase):
    def test_wyjscie_czeka_na_ocr_przed_zamknieciem_bazy_i_qt(self):
        # Osobny proces sprawdza prawdziwe QApplication.exec() oraz wyjście
        # interpretera. Zdarzenia wymuszają wyjście z aktywnym zadaniem.
        skrypt = textwrap.dedent("""\
            from pathlib import Path
            from threading import Event
            from unittest.mock import patch
            import os

            from PySide6.QtCore import QTimer
            from PySide6.QtGui import QPainter, QPdfWriter
            import shiboken6
            import main

            gotowe = Event()
            zamknieto = Event()
            zakonczono_ocr = Event()
            okna = []
            strony_po_zamknieciu = []

            def odczytaj(_sciezka, _obszar, *, przerwij):
                gotowe.set()
                if zamknieto.wait(4) and przerwij.is_set():
                    # Symuluje końcowe zwalnianie aktywnej rasteryzacji.
                    Event().wait(0.15)
                    zakonczono_ocr.set()

            pokaz = main.OknoGlowne.showEvent
            zamknij = main.OknoGlowne.closeEvent
            zamknij_baze = main.RejestrRachunkow.zamknij

            def sprawdz_baze(rejestr):
                try:
                    assert zakonczono_ocr.is_set(), "SQLite zamknięto podczas OCR"
                    assert okna and not shiboken6.isValid(okna[0]), "Okno nadal istnieje"
                finally:
                    zamknij_baze(rejestr)

            def zamknij_okno(okno, event):
                zamknij(okno, event)
                strony_po_zamknieciu.append(okno.podglad.liczba_stron)
                zamknieto.set()

            def pokaz_okno(okno, event):
                pokaz(okno, event)
                if okna:
                    return
                okna.append(okno)

                def rozpocznij():
                    plik = Path(os.environ["SWISTAK_DATA_DIR"]).parent / "syntetyczny.pdf"
                    pdf = QPdfWriter(str(plik))
                    painter = QPainter(pdf)
                    painter.drawText(100, 100, "Syntetyczny dokument")
                    painter.end()
                    del pdf
                    okno.otworz_pdf(plik)
                    okno._start_odczytu(False)
                    okno._pokaz_statystyki()
                    if gotowe.wait(4):
                        okno.close()
                    else:
                        main.QApplication.exit(2)

                QTimer.singleShot(0, rozpocznij)

            with (
                patch.object(main.OknoGlowne, "showEvent", pokaz_okno),
                patch.object(main.OknoGlowne, "closeEvent", zamknij_okno),
                patch.object(main.RejestrRachunkow, "zamknij", sprawdz_baze),
                patch("gui.odczyt_worker.odczytaj_pdf", odczytaj),
            ):
                assert main.main() == 0
            assert strony_po_zamknieciu == [0], "Otwarty uchwyt QtPdf"
        """)
        with tempfile.TemporaryDirectory() as tymczasowy:
            root = Path(tymczasowy)
            wynik = subprocess.run(
                [sys.executable, "-X", "faulthandler", "-c", skrypt],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
                     "SWISTAK_DATA_DIR": str(root / "dane"),
                     "XDG_CONFIG_HOME": str(root / "config")},
                capture_output=True, text=True, timeout=15, check=False,
            )
        self.assertEqual(wynik.returncode, 0, wynik.stdout + wynik.stderr)
        self.assertNotIn("shared QObject was deleted directly", wynik.stderr)
