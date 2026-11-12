# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Akceptacyjny test przywrócenia z GUI — wyłącznie syntetyczne dane."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

import ustawienia
from gui.okno_glowne import OknoGlowne
from i18n import set_language
from uslugi.kopie_zapasowe import utworz_kopie
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
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    pdf = base / "wylacznie-syntetyczna.pdf"
                    pdf_bytes = b"%PDF-1.4\n% FAKE invoice - not a real customer\n%%EOF\n"
                    pdf.write_bytes(pdf_bytes)
                    doc, _ = reg.importuj_pdf(pdf)
                    category = int(reg.kategorie()[0]["id"])
                    reg.zapisz_rachunek(DaneRachunku(
                        dokument_id=doc, dostawca="FIKCYJNY DOSTAWCA",
                        numer="FAKE/2026/12", kwota="13,37", kategoria_id=category
                    ))
                    archive = base / "bezpieczna-kopia.zip"
                    utworz_kopie(reg, archive, ustawienia=settings)
                    # Zmieniamy bieżące dane po backupie.
                    reg.dodaj_kategorie("Streaming demo")
                    ustawienia.save({"language": "en", "ollama_model": "qwen3:8b"})
                    previous_window = OknoGlowne(reg)
                    previous_window.show()
                    self.app.processEvents()
                    old_visible_on_new_show = []
                    original_show = OknoGlowne.show

                    def observe_show(window):
                        old_visible_on_new_show.append(previous_window.isVisible())
                        return original_show(window)

                    with (
                        patch("gui.okno_glowne.QFileDialog.getOpenFileName",
                              return_value=(str(archive), "ZIP")),
                        patch.object(QMessageBox, "question",
                                     return_value=QMessageBox.StandardButton.Yes),
                        patch.object(QMessageBox, "information"),
                        patch.object(OknoGlowne, "show", observe_show),
                    ):
                        previous_window._przywroc_kopie()
                    restored_window = previous_window._okno_po_przywroceniu
                    self.assertIsNotNone(restored_window)
                    self.assertEqual(old_visible_on_new_show, [False])
                    self.assertFalse(previous_window.isVisible())
                    self.assertTrue(restored_window.isVisible())
                    self.assertEqual(ustawienia.load()["ollama_model"], "gemma3:4b")
                    self.assertEqual(reg.rachunek(doc)["kwota_grosze"], 1337)
                    self.assertEqual(reg.sciezka_pdf(doc).read_bytes(), pdf_bytes)
                    names = [row["nazwa"] for row in reg.kategorie()]
                    self.assertNotIn("Streaming demo", names)
                    backups = list(base.glob("dane-przed-przywroceniem-*"))
                    self.assertEqual(len(backups), 1)
                    self.assertTrue((backups[0] / "swistak.sqlite3").is_file())
            finally:
                if restored_window is not None:
                    restored_window.close()
                if previous_window is not None:
                    previous_window.close()
                reg.zamknij()


if __name__ == "__main__":
    unittest.main()
