# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""GUI: czyszczenie tylko po kopii i trzech świadomych krokach."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog

import ustawienia
from testy.pomoc_qt import zamknij_widget
from gui.okno_glowne import OknoGlowne
from i18n import set_language
from uslugi.czyszczenie_bazy import podmien_na_pusta
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
        writer = QPdfWriter(str(file))
        painter = QPainter(writer)
        painter.drawText(100, 120, "Syntetyczna faktura testowa")
        self.assertTrue(painter.end())
        doc, _ = reg.importuj_pdf(file)
        reg.zapisz_rachunek(DaneRachunku(
            dokument_id=doc, dostawca="DEMO", numer="TEST/2026",
            kwota="99,22", kategoria_id=int(reg.kategorie()[0]["id"]),
            data_wystawienia="2026-11-02",
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
                            with patch("gui.operacje_danych.QFileDialog.getSaveFileName") as choose:
                                win.operacje_danych.wyczysc_baze()
                                choose.assert_not_called()
                        self.assertEqual(reg.rachunek(doc)["kwota_grosze"], 9922)
                        zip_path = home / "kopia-przed-resetem.zip"
                        with (
                            patch.object(QMessageBox, "warning",
                                         return_value=QMessageBox.StandardButton.Yes),
                            patch("gui.operacje_danych.QFileDialog.getSaveFileName",
                                  return_value=(str(zip_path), "ZIP")),
                            patch.object(QInputDialog, "getText",
                                         return_value=("NIE USUWAJ", True)),
                            patch.object(QMessageBox, "information"),
                        ):
                            win.operacje_danych.wyczysc_baze()
                        self.assertTrue(zip_path.is_file())
                        self.assertEqual(reg.rachunek(doc)["kwota_grosze"], 9922)
                        win.change_language("en")
                        self.assertIn("Clear database", win.akcja_wyczysc.text())
                    finally:
                        zamknij_widget(win)
            finally:
                reg.zamknij()

    def test_potwierdzony_reset_zamyka_pdf_przed_podmiana_i_zachowuje_zip(self):
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
                    old_win.kreator.otworz_fakture(doc)
                    podglad = old_win.kreator.podglad
                    self.assertEqual(podglad.liczba_stron, 1)
                    zip_path = home / "obowiazkowa-kopia.zip"
                    old_visible_on_new_show = []
                    pages_on_swap = []
                    original_show = OknoGlowne.show

                    def observe_show(window):
                        old_visible_on_new_show.append(old_win.isVisible())
                        return original_show(window)

                    def observe_swap(root, stage):
                        pages_on_swap.append(podglad.liczba_stron)
                        return podmien_na_pusta(root, stage)

                    with (
                        patch.object(QMessageBox, "warning",
                                     return_value=QMessageBox.StandardButton.Yes),
                        patch("gui.operacje_danych.QFileDialog.getSaveFileName",
                              return_value=(str(zip_path), "ZIP")),
                        patch.object(QInputDialog, "getText",
                                     return_value=("USUŃ WSZYSTKO", True)),
                        patch.object(QMessageBox, "question",
                                     return_value=QMessageBox.StandardButton.Yes),
                        patch.object(QMessageBox, "information"),
                        patch.object(OknoGlowne, "show", observe_show),
                        patch("gui.operacje_danych.podmien_na_pusta", side_effect=observe_swap),
                    ):
                        old_win.akcja_wyczysc.trigger()
                    new_win = old_win._okno_po_wyczyszczeniu
                    self.assertEqual(pages_on_swap, [0])
                    self.assertEqual(old_visible_on_new_show, [False])
                    self.assertFalse(old_win.isVisible())
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
                    zamknij_widget(new_win)
                if old_win:
                    zamknij_widget(old_win)
                reg.zamknij()


if __name__ == "__main__":
    unittest.main()
