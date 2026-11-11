# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Graficzne O programie: widgety, języki, przyciski i fallback obrazu."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QColor, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import QApplication, QDialog

import gui.okno_o_programie as about_module
from gui.okno_o_programie import GITHUB, OknoOProgramie
import i18n


class TestOknoOProgramie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        i18n.set_language("pl")

    def test_polski_angielski_i_zamykanie(self):
        for lang, label in (("pl", "Zamknij"), ("en", "Close")):
            with self.subTest(lang=lang):
                i18n.set_language(lang)
                win = OknoOProgramie()
                self.assertIn("Świstak", win.windowTitle())
                self.assertEqual(win.close_button.text(), label)
                self.assertTrue(win.star_button.text())
                self.assertIn("PolyForm", win.license.text())
                self.assertEqual(win.features.text(), "PDF · OCR · SQLite · Ollama")
                win.close_button.click()
                self.assertEqual(win.result(), QDialog.DialogCode.Accepted)

    def test_obraz_i_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            pic = Path(tmp) / "test.jpeg"
            img = QImage(450, 200, QImage.Format.Format_RGB32)
            img.fill(0xffb57b44)
            self.assertTrue(img.save(str(pic)))
            with patch.object(about_module, "ILLUSTRATIONS", (pic,)):
                win = OknoOProgramie()
                self.assertFalse(win.hero.pixmap().isNull())
                win.close()
            with patch.object(about_module, "ILLUSTRATIONS", (Path(tmp) / "missing.jpeg",)):
                win = OknoOProgramie()
                self.assertIn("assets/about", win.hero.text())
                win.close()

    def test_repo_korzysta_wylacznie_z_jpeg(self):
        self.assertTrue(about_module.ILLUSTRATIONS)
        self.assertTrue(all(path.suffix == ".jpeg"
                            for path in about_module.ILLUSTRATIONS))
        source = about_module.ILLUSTRATIONS[-1]
        self.assertTrue(source.is_file(), source)
        dimensions = QImageReader(str(source)).size()
        self.assertGreaterEqual(dimensions.width(), 1000)
        self.assertGreaterEqual(dimensions.height(), 600)
        self.assertFalse(OknoOProgramie._find_illustration().isNull())

    def test_wysoka_rozdzielczosc_na_hidpi(self):
        original = QPixmap(2400, 1400)
        original.fill(QColor("#ae6937"))
        scaled = OknoOProgramie._scaled_for_hidpi(original, 605, 320, 2.0)
        self.assertEqual(scaled.devicePixelRatio(), 2.0)
        self.assertGreater(scaled.width(), 605)
        self.assertLessEqual(scaled.width(), 1210)
        self.assertLessEqual(scaled.height(), 640)

    def test_github_tylko_po_kliknieciu(self):
        with patch.object(about_module.QDesktopServices, "openUrl") as opening:
            win = OknoOProgramie()
            opening.assert_not_called()
            win.star_button.click()
            opening.assert_called_once()
            self.assertEqual(opening.call_args.args[0].toString(), GITHUB)
            win.close()


if __name__ == "__main__":
    unittest.main()
