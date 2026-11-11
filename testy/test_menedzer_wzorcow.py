# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Menedżer wzorców: potwierdzanie i historia wyłącznie na fikcyjnych danych."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from gui.okno_wzorcow import OknoWzorcow
from uslugi.dopasowanie_wzorca import zaproponuj_wzorzec
from uslugi.wzorce import MagazynWzorcow


class TestMenedzerWzorcow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_edycja_anulowanie_dezaktywacja_przywrocenie(self):
        with tempfile.TemporaryDirectory() as temp:
            store = MagazynWzorcow(Path(temp))
            first = store.utworz(zaproponuj_wzorzec(
                "Sprzedawca:\nOperator DEMO\nNIP 123-456-32-18\n"
                "Okres rozliczeniowy 11/2026\n",
                "Operator DEMO", "Internet",
            ))
            ui = OknoWzorcow(None, store)
            self.assertEqual(ui.lista.count(), 1)
            self.assertTrue(ui.edytuj.isEnabled())
            self.assertIn("Operator DEMO", ui.lista.currentItem().text())
            self.assertEqual(store.pobierz(first["template_id"])["revision"], 1)

            with patch("gui.okno_wzorcow.zaakceptuj_wzorzec", return_value=None):
                ui._edytuj()
            self.assertEqual(store.pobierz(first["template_id"])["revision"], 1)

            modified = dict(first, name="Operator DEMO — zmiana reguł")
            with patch("gui.okno_wzorcow.zaakceptuj_wzorzec", return_value=modified):
                ui._edytuj()
            second = store.pobierz(first["template_id"])
            self.assertEqual(second["revision"], 2)
            self.assertEqual(second["name"], "Operator DEMO — zmiana reguł")

            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Yes):
                ui._zmien_status()
            third = store.pobierz(first["template_id"])
            self.assertEqual(third["revision"], 3)
            self.assertEqual(third["status"], "inactive")
            self.assertEqual(store.lista(tylko_aktywne=True), [])

            with patch.object(QInputDialog, "getItem", return_value=("1", True)), \
                 patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Yes):
                ui._przywroc()
            fourth = store.pobierz(first["template_id"])
            self.assertEqual(fourth["revision"], 4)
            self.assertEqual(fourth["status"], "approved")
            self.assertEqual(fourth["name"], first["name"])
            self.assertTrue((store.katalog / "historia" /
                f"{first['template_id']}.rev-000003.json").is_file())
            ui.close()

    def test_nie_ma_zapisu_przy_otwarciu_formularza(self):
        with tempfile.TemporaryDirectory() as temp:
            store = MagazynWzorcow(Path(temp))
            dialog = OknoWzorcow(None, store)
            self.assertEqual(dialog.lista.count(), 0)
            self.assertFalse(dialog.edytuj.isEnabled())
            self.assertFalse(dialog.przywroc.isEnabled())
            self.assertFalse(dialog.zmien_status.isEnabled())
            self.assertFalse(store.katalog.exists())
            dialog.close()


if __name__ == "__main__":
    unittest.main()
