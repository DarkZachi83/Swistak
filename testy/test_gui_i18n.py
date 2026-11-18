# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Qt offscreen: aktywny język NIE może kasować rachunku, PDF ani stanu AI."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

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
                    kreator = okno.kreator
                    formularz = kreator.formularz
                    okno.show()
                    self.app.processEvents()
                    self.assertEqual(
                        [a.text() for a in okno.menuBar().actions()],
                        ["Plik", "Ustawienia", "Języki", "O programie"]
                    )
                    self.assertEqual(kreator.nawigacja.item(0).text(), "Odczyt PDF / skanu")
                    self.assertEqual(kreator.nawigacja.item(3).text(), "Faktura")
                    pdf = root / "demo.pdf"
                    writer = QPdfWriter(str(pdf))
                    painter = QPainter(writer)
                    self.assertTrue(painter.isActive())
                    painter.drawText(100, 100, "Syntetyczny rachunek DEMO")
                    self.assertTrue(painter.end())
                    okno.otworz_pdf(pdf)
                    page_count = kreator.podglad.liczba_stron
                    document_id = kreator.aktualny_dokument_id

                    formularz.ed_dostawca.setText("Dostawca DEMO")
                    formularz.ed_kwota.setText("123,45")
                    formularz.ed_uwagi.setPlainText("Nie zapisano")
                    kreator.pole_odczytu.setPlainText("syntetyczny OCR\ntekst")
                    gaz_id = next(int(row["id"]) for row in db.kategorie()
                                  if row["nazwa"] == "Gaz")
                    formularz.wybor_kategoria.setCurrentIndex(
                        formularz.wybor_kategoria.findData(gaz_id)
                    )
                    selected = formularz.wybor_kategoria.currentData()
                    kreator.karty.setCurrentIndex(3)
                    kreator.tabela_ai.item(0, 1).setText("TESTOWA SUGESTIA")

                    okno.change_language("en")
                    self.app.processEvents()
                    self.assertEqual(okno.menuBar().actions()[0].text(), "File")
                    self.assertEqual(okno.menuBar().actions()[2].text(), "Languages")
                    self.assertEqual(kreator.nawigacja.item(0).text(), "PDF / scan text")
                    self.assertEqual(kreator.nawigacja.item(3).text(), "Invoice")
                    self.assertEqual(kreator.btn_odczytaj.text(), "Read entire PDF")
                    self.assertEqual(formularz.nazwa_dokumentu.text(), "Original: demo.pdf")
                    self.assertEqual(formularz.wybor_status.itemText(1), i18n.t("form.status_paid"))
                    self.assertEqual(formularz.zapisz_przycisk.text(), i18n.t("button.save"))
                    self.assertEqual([label.text() for label in formularz._form_labels],
                                     [i18n.t(key) for key in formularz._FORM_KEYS])
                    self.assertEqual(formularz.ed_kwota.text(), "123,45")
                    self.assertEqual(formularz.ed_dostawca.text(), "Dostawca DEMO")
                    self.assertEqual(formularz.ed_uwagi.toPlainText(), "Nie zapisano")
                    self.assertEqual(kreator.pole_odczytu.toPlainText(), "syntetyczny OCR\ntekst")
                    self.assertEqual(kreator.tabela_ai.item(0, 1).text(), "TESTOWA SUGESTIA")
                    self.assertEqual(kreator.tabela_ai.item(0, 0).text(), "Supplier")
                    self.assertEqual(kreator.aktualny_dokument_id, document_id)
                    self.assertEqual(kreator.podglad.liczba_stron, page_count)
                    self.assertEqual(kreator.karty.currentIndex(), 3)
                    self.assertEqual(formularz.wybor_kategoria.currentData(), selected)
                    self.assertEqual(formularz.wybor_kategoria.currentText(), "Gas")
                    self.assertEqual(ustawienia.load()["language"], "en")
                    self.assertTrue(okno._lang_actions["en"].isChecked())

                    okno.change_language("pl")
                    self.assertEqual(kreator.nawigacja.item(0).text(), "Odczyt PDF / skanu")
                    self.assertEqual(kreator.nawigacja.item(3).text(), "Faktura")
                    self.assertEqual(okno.menuBar().actions()[2].text(), "Języki")
                    self.assertEqual(formularz.nazwa_dokumentu.text(), "Oryginał: demo.pdf")
                    self.assertEqual(formularz.wybor_status.itemText(1), "Opłacony")
                    self.assertEqual(formularz.zapisz_przycisk.text(), i18n.t("button.save"))
                    self.assertEqual(formularz.ed_kwota.text(), "123,45")
                    self.assertEqual(formularz.wybor_kategoria.currentText(), "Gaz")
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
                    self.assertEqual(okno.kreator.ed_model.text(), "custom:4b")
                    self.assertEqual(okno.kreator.nawigacja.item(3).text(), "Invoice")
                    self.assertEqual(okno.prefs["language"], "en")
                    self.assertTrue(okno._lang_actions["en"].isChecked())
                    okno.close()
            finally:
                db.zamknij()
                i18n.set_language("pl")


if __name__ == "__main__":
    unittest.main()
