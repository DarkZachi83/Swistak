# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Dialog kategorii: lista, podobieństwo, zgoda, odmowa i wzorce."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from gui.dialog_kategorie import DialogKategorie, DialogScalKategorie
from i18n import set_language
from uslugi.rachunki import RejestrRachunkow
from uslugi.wzorce import MagazynWzorcow


class TestDialogKategorii(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        set_language("pl")
        self.temp = tempfile.TemporaryDirectory()
        self.db = RejestrRachunkow(Path(self.temp.name) / "dane")
        self.wzorce = MagazynWzorcow(self.db.katalog)

    def tearDown(self):
        self.db.zamknij()
        self.temp.cleanup()
        set_language("pl")

    def test_lista_istniejacych_i_wybor_bez_tworzenia_nowej(self):
        dialog = DialogKategorie(self.db, self.wzorce)
        self.assertEqual(dialog.lista.count(), 6)
        self.assertIn("faktur", dialog.lista.item(0).text())
        dialog.lista.setCurrentRow(0)
        selected = dialog.lista.currentItem().data(256)  # Qt.UserRole
        dialog._wybierz()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.wybrana_id, selected)
        self.assertEqual(len(self.db.kategorie()), 6)
        dialog.close()

    def test_literowka_pokazuje_podpowiedz_i_wymaga_zgody(self):
        dialog = DialogKategorie(self.db, self.wzorce)
        dialog.nowa.setText("Energi")
        self.assertIn("Energia elektryczna", dialog.podobne.text())
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No):
            dialog._dodaj()
        self.assertEqual(len(self.db.kategorie()), 6)
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            dialog._dodaj()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIn(dialog.wybrana_id, [int(x["id"]) for x in self.db.kategorie()])
        self.assertEqual(len(self.db.kategorie()), 7)
        dialog.close()

    def test_nazwa_rownowazna_nie_tworzy_drugiej(self):
        dialog = DialogKategorie(self.db, self.wzorce)
        dialog.nowa.setText("energia-elektryczna")
        with patch.object(QMessageBox, "information") as info:
            dialog._dodaj()
            info.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(self.db.kategorie()), 6)
        dialog.close()

    def test_wzorzec_zalezy_od_nazwy_i_blokuje_scalanie(self):
        source = self.db.dodaj_kategorie("Energi", zezwol_na_podobna=True)
        target = next(int(row["id"]) for row in self.db.kategorie()
                      if row["nazwa"] == "Energia elektryczna")
        dialog = DialogScalKategorie(self.db, self.wzorce)
        dialog.zrodlo.setCurrentIndex(dialog.zrodlo.findData(source))
        dialog.cel.setCurrentIndex(dialog.cel.findData(target))
        self.assertTrue(dialog.btn_scal.isEnabled())
        self.assertIn("0", dialog.info.text())
        with patch.object(self.wzorce, "lista", return_value=[
            {"name": "WZORZEC TESTOWY", "category": "Energi"}
        ]):
            with patch.object(QMessageBox, "warning") as warn:
                dialog._wykonaj()
                warn.assert_called_once()
        self.assertIn(source, [int(row["id"]) for row in self.db.kategorie()])
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No):
            dialog._wykonaj()
        self.assertIn(source, [int(row["id"]) for row in self.db.kategorie()])
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes):
            dialog._wykonaj()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.wybrany_cel, target)
        self.assertNotIn(source, [int(row["id"]) for row in self.db.kategorie()])
        dialog.close()


if __name__ == "__main__":
    unittest.main()
