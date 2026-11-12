# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""GUI: wybór modelu nie dotyka bazy i nie wybiera obcych plików GGUF."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog

import ustawienia
from gui.dialog_modele_lokalne import DialogModeleLokalne
from gui.okno_glowne import OknoGlowne
from i18n import set_language
from uslugi.modele_lokalne import ModelNaDysku
from uslugi.rachunki import RejestrRachunkow


class TestDialogLokalnychModeli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_language("pl")

    def test_tylko_ollama_pozwala_zatwierdzic(self):
        with patch("gui.dialog_modele_lokalne.QThreadPool.globalInstance"):
            dialog = DialogModeleLokalne()
        try:
            disk = [ModelNaDysku("test-model", "LM Studio", Path("/tmp/synthetic.gguf"))]
            dialog._gotowe(["gemma3:4b", "qwen3:8b"], disk, "")
            self.assertEqual(dialog.lista_ollama.count(), 2)
            self.assertEqual(dialog.lista_dysk.count(), 1)
            dialog.lista_ollama.setCurrentRow(1)
            self.assertTrue(dialog.btn_uzyj.isEnabled())
            dialog.karty.setCurrentIndex(1)
            self.assertFalse(dialog.btn_uzyj.isEnabled())
            dialog._zatwierdz()
            self.assertIsNone(dialog.wybrany_model)
            dialog.karty.setCurrentIndex(0)
            dialog._zatwierdz()
            self.assertEqual(dialog.wybrany_model, "qwen3:8b")
        finally:
            dialog.close()

    def test_blad_ollamy_pokazuje_dysk_bez_pozornej_gotowosci(self):
        with patch("gui.dialog_modele_lokalne.QThreadPool.globalInstance"):
            dialog = DialogModeleLokalne()
        try:
            disk = [ModelNaDysku("gemma3:4b", "Ollama", Path("/tmp/fictional"))]
            dialog._gotowe([], disk, "Ollama nie działa")
            self.assertFalse(dialog.btn_uzyj.isEnabled())
            self.assertEqual(dialog.lista_dysk.count(), 1)
            self.assertIn("Ollama", dialog.status.text())
        finally:
            dialog.close()

    def test_wybor_zapisuje_model_do_ustawien(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = RejestrRachunkow(root / "data")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "settings.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    try:
                        with patch("gui.okno_glowne.DialogModeleLokalne") as dialog:
                            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
                            dialog.return_value.wybrany_model = "qwen3:8b"
                            win.btn_szukaj_modeli.click()
                        self.assertEqual(win.ed_model.text(), "qwen3:8b")
                        self.assertEqual(ustawienia.load()["ollama_model"], "qwen3:8b")
                        self.assertEqual(db.db.execute(
                            "SELECT COUNT(*) FROM rachunki"
                        ).fetchone()[0], 0)
                        win.change_language("en")
                        self.assertIn("Find local models", win.btn_szukaj_modeli.text())
                        self.assertEqual(win.ed_model.text(), "qwen3:8b")
                        with patch("gui.okno_glowne.DialogModeleLokalne") as dialog:
                            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
                            win.btn_szukaj_modeli.click()
                        self.assertEqual(win.ed_model.text(), "qwen3:8b")
                    finally:
                        win.close()
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
