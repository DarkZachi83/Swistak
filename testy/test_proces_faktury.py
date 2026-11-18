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
from testy.pomoc_qt import zamknij_widget
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
                    kreator = win.kreator
                    formularz = kreator.formularz
                    win.show()
                    self.app.processEvents()
                    self.assertEqual(kreator.nawigacja.count(), 5)
                    self.assertEqual(kreator.karty.count(), 5)
                    self.assertEqual(
                        [kreator.nawigacja.item(i).text() for i in range(5)],
                        ["Odczyt PDF / skanu", "Analiza AI", "Edycja danych",
                         "Faktura", "Dokumenty"]
                    )
                    self.assertEqual(kreator.karty.currentIndex(), kreator.ETAP_ODCZYT)
                    self.assertEqual(kreator.tabela_ai.horizontalHeader().sectionResizeMode(2),
                                     QHeaderView.ResizeMode.Stretch)

                    win.otworz_pdf(pdf)
                    document_id = kreator.aktualny_dokument_id
                    self.assertIsNotNone(document_id)
                    self.assertIsNone(db.rachunek(document_id))

                    kreator.nawigacja.setCurrentRow(kreator.ETAP_EDYCJA)
                    self.assertEqual(kreator.karty.currentIndex(), kreator.ETAP_EDYCJA)
                    formularz.ed_dostawca.setText("DEMO Sp. z o.o.")
                    formularz.ed_numer.setText("FAKTURA-SZTUCZNA-2026")
                    formularz.ed_kwota.setText("98,76")
                    formularz.ed_wystawiono.setText("2026-11-02")
                    formularz.ed_uwagi.setPlainText("Test korekty — bez danych klienta")
                    formularz.wybor_kategoria.setCurrentIndex(1)

                    formularz.btn_przejdz_faktura.click()
                    self.assertEqual(kreator.karty.currentIndex(), kreator.ETAP_FAKTURA)
                    self.assertEqual(kreator.nawigacja.currentRow(), kreator.ETAP_FAKTURA)
                    self.assertEqual(formularz.podsumowanie_wartosci["kwota"].text(), "98,76")
                    self.assertEqual(formularz.podsumowanie_wartosci["numer"].text(),
                                     "FAKTURA-SZTUCZNA-2026")
                    self.assertIsNone(db.rachunek(document_id))  # podgląd nie zapisuje

                    formularz.btn_powrot_edycja.click()
                    self.assertEqual(kreator.karty.currentIndex(), kreator.ETAP_EDYCJA)
                    self.assertEqual(formularz.ed_kwota.text(), "98,76")
                    formularz.ed_kwota.setText("89,67")
                    kreator.karty.setCurrentIndex(kreator.ETAP_FAKTURA)
                    self.assertEqual(formularz.podsumowanie_wartosci["kwota"].text(), "89,67")
                    self.assertIsNone(db.rachunek(document_id))

                    formularz.zapisz_przycisk.click()
                    self.assertEqual(db.rachunek(document_id)["kwota_grosze"], 8967)
                    self.assertIn("zapisana", formularz.info_faktury.text())
                    win.change_language("en")
                    self.assertIn("has been saved", formularz.info_faktury.text())
                    win.change_language("pl")
                    self.assertIn("zapisana", formularz.info_faktury.text())
                    zamknij_widget(win)
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
                    kreator = win.kreator
                    formularz = kreator.formularz
                    kreator.nawigacja.setCurrentRow(kreator.ETAP_EDYCJA)
                    formularz.ed_dostawca.setText("WYŁĄCZNIE SYNTETYCZNE")
                    formularz.ed_kwota.setText("12,34")
                    win.change_language("en")
                    self.assertEqual(kreator.nawigacja.item(3).text(), "Invoice")
                    self.assertEqual(kreator.nawigacja.currentRow(), kreator.ETAP_EDYCJA)
                    self.assertEqual(formularz.ed_dostawca.text(), "WYŁĄCZNIE SYNTETYCZNE")
                    self.assertEqual(formularz.ed_kwota.text(), "12,34")
                    zamknij_widget(win)
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
