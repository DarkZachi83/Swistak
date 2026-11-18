# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Akceptacyjny test przywrócenia z GUI — wyłącznie syntetyczne dane."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QMessageBox

import ustawienia
from testy.pomoc_qt import zamknij_widget
from gui.okno_glowne import OknoGlowne
from i18n import set_language
from uslugi.kopie_zapasowe import podmien_dane, utworz_kopie
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class TestPrzywracaniePrzezGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_language("pl")

    def test_przywrocenie_resetuje_widok_i_zachowuje_stare_dane(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            data = base / "dane"
            settings = base / "prefs.json"
            reg = RejestrRachunkow(data)
            previous_window = None
            restored_window = None
            try:
                with patch.object(ustawienia, "path_settings", return_value=settings):
                    backup_prefs = {
                        "language": "pl", "ollama_model": "gemma3:4b",
                        "model_scan_dir": str(base / "testowe-modele"),
                        "model_extractor": "demo-ekstrakcja:1",
                        "model_verifier": "demo-weryfikacja:2",
                        "model_financial_analyst": "",
                        "model_cycle_analyst": "demo-cykl:4",
                    }
                    ustawienia.save(backup_prefs)
                    pdf = base / "wylacznie-syntetyczna.pdf"
                    writer = QPdfWriter(str(pdf))
                    painter = QPainter(writer)
                    painter.drawText(100, 120, "Syntetyczna faktura testowa")
                    self.assertTrue(painter.end())
                    pdf_bytes = pdf.read_bytes()
                    doc, _ = reg.importuj_pdf(pdf)
                    category = int(reg.kategorie()[0]["id"])
                    reg.zapisz_rachunek(DaneRachunku(
                        dokument_id=doc, dostawca="FIKCYJNY DOSTAWCA",
                        numer="FAKE/2026/12", kwota="13,37", kategoria_id=category,
                        data_wystawienia="2026-12-02",
                    ))
                    archive = base / "bezpieczna-kopia.zip"
                    utworz_kopie(reg, archive, ustawienia=settings)
                    # Zmieniamy bieżące dane po backupie.
                    reg.dodaj_kategorie("Streaming demo")
                    ustawienia.save({
                        "language": "en", "ollama_model": "qwen3:8b",
                        "model_financial_analyst": "po-kopii:1",
                    })
                    previous_window = OknoGlowne(reg)
                    previous_window.show()
                    self.app.processEvents()
                    previous_window.otworz_pdf(pdf)
                    podglad = previous_window.kreator.podglad
                    self.assertEqual(podglad.liczba_stron, 1)
                    old_visible_on_new_show = []
                    pages_on_replace = []
                    original_show = OknoGlowne.show

                    def observe_show(window):
                        old_visible_on_new_show.append(previous_window.isVisible())
                        return original_show(window)

                    def observe_replace(kopia, folder):
                        pages_on_replace.append(podglad.liczba_stron)
                        return podmien_dane(kopia, folder)

                    with (
                        patch("gui.operacje_danych.QFileDialog.getOpenFileName",
                              return_value=(str(archive), "ZIP")),
                        patch.object(QMessageBox, "question",
                                     return_value=QMessageBox.StandardButton.Yes),
                        patch.object(QMessageBox, "information"),
                        patch.object(OknoGlowne, "show", observe_show),
                        patch("gui.operacje_danych.podmien_dane", side_effect=observe_replace),
                    ):
                        previous_window.akcja_przywroc.trigger()
                    restored_window = previous_window._okno_po_przywroceniu
                    self.assertIsNotNone(restored_window)
                    self.assertEqual(pages_on_replace, [0])
                    self.assertEqual(old_visible_on_new_show, [False])
                    self.assertFalse(previous_window.isVisible())
                    self.assertTrue(restored_window.isVisible())
                    self.assertEqual(ustawienia.load(), backup_prefs)
                    self.assertEqual(restored_window.prefs, backup_prefs)
                    self.assertEqual(reg.rachunek(doc)["kwota_grosze"], 1337)
                    self.assertEqual(reg.sciezka_pdf(doc).read_bytes(), pdf_bytes)
                    names = [row["nazwa"] for row in reg.kategorie()]
                    self.assertNotIn("Streaming demo", names)
                    backups = list(base.glob("dane-przed-przywroceniem-*"))
                    self.assertEqual(len(backups), 1)
                    self.assertTrue((backups[0] / "swistak.sqlite3").is_file())
            finally:
                if restored_window is not None:
                    zamknij_widget(restored_window)
                if previous_window is not None:
                    zamknij_widget(previous_window)
                reg.zamknij()


if __name__ == "__main__":
    unittest.main()
