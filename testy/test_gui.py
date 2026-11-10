# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Test okna PySide6 na wytworzonym w locie PDF."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication
from gui.okno_glowne import OknoGlowne
from uslugi.rachunki import RejestrRachunkow


class TestGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_import_zapis_odczyt_formularza(self):
        with tempfile.TemporaryDirectory() as katalog:
            root = Path(katalog)
            pdf = root / "testowy.pdf"
            writer = QPdfWriter(str(pdf))
            painter = QPainter(writer)
            self.assertTrue(painter.isActive())
            painter.drawText(100, 120, "Syntetyczny dokument testowy")
            self.assertTrue(painter.end())

            rejestr = RejestrRachunkow(root / "dane")
            try:
                okno = OknoGlowne(rejestr)
                okno.show()
                self.app.processEvents()
                okno.otworz_pdf(pdf)
                self.assertIsNotNone(okno.aktualny_dokument_id)
                dokument = okno.aktualny_dokument_id
                self.assertEqual(len(rejestr.dokumenty()), 1)
                okno.ed_dostawca.setText("Dostawca testowy")
                okno.ed_kwota.setText("19,99")
                okno.wybor_kategoria.setCurrentIndex(1)
                okno._zapisz_rachunek()
                self.assertEqual(rejestr.rachunek(dokument)["kwota_grosze"], 1999)
                okno._wyswietl_dokument(dokument)
                self.assertEqual(okno.ed_dostawca.text(), "Dostawca testowy")
                self.assertEqual(okno.ed_kwota.text(), "19,99")
                okno.close()
            finally:
                rejestr.zamknij()


if __name__ == "__main__":
    unittest.main()
