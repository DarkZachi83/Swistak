# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Przepływ pracy na całkowicie syntetycznej fakturze — bez prawdziwych danych."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QHeaderView

import ustawienia
from gui.okno_glowne import OknoGlowne
from uslugi.rachunki import RejestrRachunkow


class TestProcesFaktury(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _syntetyczny_pdf(path: Path) -> None:
        writer = QPdfWriter(str(path))
        painter = QPainter(writer)
        if not painter.isActive():
            raise RuntimeError("Nie można wygenerować PDF testowego")
        painter.drawText(100, 120, "Syntetyczna faktura DEMO")
        painter.end()

    def test_pionowa_nawigacja_i_swiadomy_zapis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "syntetyczna-faktura.pdf"
            self._syntetyczny_pdf(pdf)
            db = RejestrRachunkow(root / "prywatne-dane-testowe")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "settings.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    win.show()
                    self.app.processEvents()
                    self.assertEqual(win.nawigacja.count(), 5)
                    self.assertEqual(win.karty.count(), 5)
                    self.assertEqual(
                        [win.nawigacja.item(i).text() for i in range(5)],
                        ["Odczyt PDF / skanu", "Analiza AI", "Edycja danych",
                         "Faktura", "Dokumenty"]
                    )
                    self.assertEqual(win.karty.currentIndex(), win.ETAP_ODCZYT)
                    self.assertEqual(win.tabela_ai.horizontalHeader().sectionResizeMode(2),
                                     QHeaderView.ResizeMode.Stretch)

                    win.otworz_pdf(pdf)
                    document_id = win.aktualny_dokument_id
                    self.assertIsNotNone(document_id)
                    self.assertIsNone(db.rachunek(document_id))

                    win.nawigacja.setCurrentRow(win.ETAP_EDYCJA)
                    self.assertEqual(win.karty.currentIndex(), win.ETAP_EDYCJA)
                    win.ed_dostawca.setText("DEMO Sp. z o.o.")
                    win.ed_numer.setText("FAKTURA-SZTUCZNA-2026")
                    win.ed_kwota.setText("98,76")
                    win.ed_uwagi.setPlainText("Test korekty — bez danych klienta")
                    win.wybor_kategoria.setCurrentIndex(1)

                    win.btn_przejdz_faktura.click()
                    self.assertEqual(win.karty.currentIndex(), win.ETAP_FAKTURA)
                    self.assertEqual(win.nawigacja.currentRow(), win.ETAP_FAKTURA)
                    self.assertEqual(win.podsumowanie_wartosci["kwota"].text(), "98,76")
                    self.assertEqual(win.podsumowanie_wartosci["numer"].text(),
                                     "FAKTURA-SZTUCZNA-2026")
                    self.assertIsNone(db.rachunek(document_id))  # podgląd nie zapisuje

                    win.btn_powrot_edycja.click()
                    self.assertEqual(win.karty.currentIndex(), win.ETAP_EDYCJA)
                    self.assertEqual(win.ed_kwota.text(), "98,76")
                    win.ed_kwota.setText("89,67")
                    win.karty.setCurrentIndex(win.ETAP_FAKTURA)
                    self.assertEqual(win.podsumowanie_wartosci["kwota"].text(), "89,67")
                    self.assertIsNone(db.rachunek(document_id))

                    win.zapisz_przycisk.click()
                    self.assertEqual(db.rachunek(document_id)["kwota_grosze"], 8967)
                    self.assertIn("zapisana", win.info_faktury.text())
                    win.close()
            finally:
                db.zamknij()

    def test_zmiana_jezyka_nie_czysci_edytowanych_danych(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "ustawienia.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    win.nawigacja.setCurrentRow(win.ETAP_EDYCJA)
                    win.ed_dostawca.setText("WYŁĄCZNIE SYNTETYCZNE")
                    win.ed_kwota.setText("12,34")
                    win.change_language("en")
                    self.assertEqual(win.nawigacja.item(3).text(), "Invoice")
                    self.assertEqual(win.nawigacja.currentRow(), win.ETAP_EDYCJA)
                    self.assertEqual(win.ed_dostawca.text(), "WYŁĄCZNIE SYNTETYCZNE")
                    self.assertEqual(win.ed_kwota.text(), "12,34")
                    win.close()
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
