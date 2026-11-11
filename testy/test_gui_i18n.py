# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Qt offscreen: aktywny język NIE może kasować rachunku, PDF ani stanu AI."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

import i18n
import ustawienia
from gui.okno_glowne import OknoGlowne
from uslugi.rachunki import RejestrRachunkow


class TestQtJezyki(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_menu_i_zmiana_bez_znikania_danych(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = RejestrRachunkow(root / "dane")
            settings = root / "config" / "settings.json"
            try:
                with patch.object(ustawienia, "path_settings", return_value=settings):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    okno = OknoGlowne(db)
                    okno.show()
                    self.app.processEvents()
                    self.assertEqual(
                        [a.text() for a in okno.menuBar().actions()],
                        ["Plik", "Ustawienia", "Języki", "O programie"]
                    )
                    self.assertEqual(okno.nawigacja.item(0).text(), "Odczyt PDF / skanu")
                    self.assertEqual(okno.nawigacja.item(3).text(), "Faktura")
                    pdf = root / "demo.pdf"
                    writer = QPdfWriter(str(pdf))
                    painter = QPainter(writer)
                    self.assertTrue(painter.isActive())
                    painter.drawText(100, 100, "Syntetyczny rachunek DEMO")
                    self.assertTrue(painter.end())
                    okno.otworz_pdf(pdf)
                    page_count = okno.podglad.liczba_stron
                    document_id = okno.aktualny_dokument_id

                    okno.ed_dostawca.setText("Dostawca DEMO")
                    okno.ed_kwota.setText("123,45")
                    okno.ed_uwagi.setPlainText("Nie zapisano")
                    okno.pole_odczytu.setPlainText("syntetyczny OCR\ntekst")
                    gaz_id = next(int(row["id"]) for row in db.kategorie()
                                  if row["nazwa"] == "Gaz")
                    okno.wybor_kategoria.setCurrentIndex(
                        okno.wybor_kategoria.findData(gaz_id)
                    )
                    selected = okno.wybor_kategoria.currentData()
                    okno.karty.setCurrentIndex(3)
                    okno.tabela_ai.item(0, 1).setText("TESTOWA SUGESTIA")

                    okno.change_language("en")
                    self.app.processEvents()
                    self.assertEqual(okno.menuBar().actions()[0].text(), "File")
                    self.assertEqual(okno.menuBar().actions()[2].text(), "Languages")
                    self.assertEqual(okno.nawigacja.item(0).text(), "PDF / scan text")
                    self.assertEqual(okno.nawigacja.item(3).text(), "Invoice")
                    self.assertEqual(okno.btn_odczytaj.text(), "Read entire PDF")
                    self.assertEqual(okno.ed_kwota.text(), "123,45")
                    self.assertEqual(okno.ed_dostawca.text(), "Dostawca DEMO")
                    self.assertEqual(okno.ed_uwagi.toPlainText(), "Nie zapisano")
                    self.assertEqual(okno.pole_odczytu.toPlainText(), "syntetyczny OCR\ntekst")
                    self.assertEqual(okno.tabela_ai.item(0, 1).text(), "TESTOWA SUGESTIA")
                    self.assertEqual(okno.tabela_ai.item(0, 0).text(), "Supplier")
                    self.assertEqual(okno.aktualny_dokument_id, document_id)
                    self.assertEqual(okno.podglad.liczba_stron, page_count)
                    self.assertEqual(okno.karty.currentIndex(), 3)
                    self.assertEqual(okno.wybor_kategoria.currentData(), selected)
                    self.assertEqual(okno.wybor_kategoria.currentText(), "Gas")
                    self.assertEqual(ustawienia.load()["language"], "en")
                    self.assertTrue(okno._lang_actions["en"].isChecked())

                    okno.change_language("pl")
                    self.assertEqual(okno.nawigacja.item(0).text(), "Odczyt PDF / skanu")
                    self.assertEqual(okno.nawigacja.item(3).text(), "Faktura")
                    self.assertEqual(okno.menuBar().actions()[2].text(), "Języki")
                    self.assertEqual(okno.ed_kwota.text(), "123,45")
                    self.assertEqual(okno.wybor_kategoria.currentText(), "Gaz")
                    self.assertEqual(ustawienia.load()["language"], "pl")

                    okno.close()
            finally:
                db.zamknij()
                i18n.set_language("pl")

    def test_wyjscie_bez_zmian_w_sesji(self):
        with tempfile.TemporaryDirectory() as td:
            db = RejestrRachunkow(Path(td) / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=Path(td) / "prefs.json"):
                    ustawienia.save({"language": "en", "ollama_model": "custom:4b"})
                    okno = OknoGlowne(db)
                    self.assertEqual(okno.ed_model.text(), "custom:4b")
                    self.assertEqual(okno.nawigacja.item(3).text(), "Invoice")
                    self.assertEqual(okno.prefs["language"], "en")
                    self.assertTrue(okno._lang_actions["en"].isChecked())
                    okno.close()
            finally:
                db.zamknij()
                i18n.set_language("pl")


if __name__ == "__main__":
    unittest.main()
