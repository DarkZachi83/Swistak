# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Okno kopii — kontrola menu i niezależności od rzeczywistych danych."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

import ustawienia
from gui.okno_glowne import OknoGlowne
from i18n import set_language
from uslugi.rachunki import RejestrRachunkow


class TestBackupMenu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_language("pl")

    def test_menu_dwujezyczne_i_odmowa_nie_tworzy_pliku(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "settings.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    try:
                        self.assertIn("kopię", win.akcja_kopia.text())
                        self.assertIn("Przywróć", win.akcja_przywroc.text())
                        archive = root / "backup.zip"
                        with patch("gui.okno_glowne.QFileDialog.getSaveFileName",
                                   return_value=(str(archive), "ZIP")):
                            with patch.object(QMessageBox, "question",
                                              return_value=QMessageBox.StandardButton.No):
                                win.akcja_kopia.trigger()
                        self.assertFalse(archive.exists())
                        win.change_language("en")
                        self.assertIn("Create backup", win.akcja_kopia.text())
                        self.assertIn("Restore backup", win.akcja_przywroc.text())
                    finally:
                        win.close()
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
