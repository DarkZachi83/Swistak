# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""GUI: czyszczenie tylko po kopii i trzech świadomych krokach."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog

import ustawienia
from gui.okno_glowne import OknoGlowne
from i18n import set_language
from uslugi.kopie_zapasowe import przygotuj_przywracanie
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class TestWyczyscBazeGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_language("pl")

    def _use_fake_invoice(self, home, reg):
        file = home / "syntetyczny.pdf"
        file.write_bytes(b"%PDF-1.4\n% FIKCYJNE KOSZTY\n%%EOF\n")
        doc, _ = reg.importuj_pdf(file)
        reg.zapisz_rachunek(DaneRachunku(
            dokument_id=doc, dostawca="DEMO", numer="TEST/2026",
            kwota="99,22", kategoria_id=int(reg.kategorie()[0]["id"]),
        ))
        return doc

    def test_odmowa_i_bledna_fraza_nie_czyszcza(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            reg = RejestrRachunkow(home / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=home / "settings.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    doc = self._use_fake_invoice(home, reg)
                    win = OknoGlowne(reg)
                    try:
                        self.assertIn("Wyczyść", win.akcja_wyczysc.text())
                        with patch.object(QMessageBox, "warning",
                                          return_value=QMessageBox.StandardButton.No):
                            with patch("gui.okno_glowne.QFileDialog.getSaveFileName") as choose:
                                win._wyczysc_baze()
                                choose.assert_not_called()
                        self.assertEqual(reg.rachunek(doc)["kwota_grosze"], 9922)
                        zip_path = home / "kopia-przed-resetem.zip"
                        with (
                            patch.object(QMessageBox, "warning",
                                         return_value=QMessageBox.StandardButton.Yes),
                            patch("gui.okno_glowne.QFileDialog.getSaveFileName",
                                  return_value=(str(zip_path), "ZIP")),
                            patch.object(QInputDialog, "getText",
                                         return_value=("NIE USUWAJ", True)),
                            patch.object(QMessageBox, "information"),
                        ):
                            win._wyczysc_baze()
                        self.assertTrue(zip_path.is_file())
                        self.assertEqual(reg.rachunek(doc)["kwota_grosze"], 9922)
                        win.change_language("en")
                        self.assertIn("Clear database", win.akcja_wyczysc.text())
                    finally:
                        win.close()
            finally:
                reg.zamknij()

    def test_potwierdzony_reset_pusty_stan_i_zachowany_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            data = home / "dane"
            reg = RejestrRachunkow(data)
            old_win = None
            new_win = None
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=home / "settings.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    doc = self._use_fake_invoice(home, reg)
                    reg.dodaj_kategorie("Wlasna testowa")
                    (data / "wzorce").mkdir()
                    (data / "wzorce" / "fikcyjny.json").write_text('{"demo":true}')
                    old_win = OknoGlowne(reg)
                    old_win.show()
                    self.app.processEvents()
                    zip_path = home / "obowiazkowa-kopia.zip"
                    with (
                        patch.object(QMessageBox, "warning",
                                     return_value=QMessageBox.StandardButton.Yes),
                        patch("gui.okno_glowne.QFileDialog.getSaveFileName",
                              return_value=(str(zip_path), "ZIP")),
                        patch.object(QInputDialog, "getText",
                                     return_value=("USUŃ WSZYSTKO", True)),
                        patch.object(QMessageBox, "question",
                                     return_value=QMessageBox.StandardButton.Yes),
                        patch.object(QMessageBox, "information"),
                    ):
                        old_win._wyczysc_baze()
                    new_win = old_win._okno_po_wyczyszczeniu
                    self.assertTrue(new_win.isVisible())
                    self.assertEqual(reg.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 0)
                    self.assertEqual(reg.db.execute("SELECT COUNT(*) FROM dokumenty").fetchone()[0], 0)
                    self.assertEqual(len(reg.kategorie()), 6)
                    self.assertFalse((data / "wzorce").exists())
                    self.assertEqual(list(data.glob("dokumenty/**/*.pdf")), [])
                    self.assertEqual(list(home.glob("dane-przed-wyczyszczeniem-*")), [])
                    self.assertEqual(ustawienia.load()["ollama_model"], "gemma3:4b")
                    self.assertTrue(zip_path.is_file())
                    back = przygotuj_przywracanie(zip_path, data)
                    try:
                        self.assertEqual(back.opis.dokumenty_pdf, 1)
                    finally:
                        back.sprzataj()
            finally:
                if new_win:
                    new_win.close()
                if old_win:
                    old_win.close()
                reg.zamknij()


if __name__ == "__main__":
    unittest.main()
