# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""GUI rejestru faktur: sortowanie, filtrowanie, otwieranie i tłumaczenia."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QMessageBox

import ustawienia
from gui.okno_glowne import OknoGlowne
from gui.tabela_faktur import TabelaFaktur
from i18n import set_language
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class TestTabelaFaktur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def fake_pdf(path: Path):
        painter = QPainter()
        writer = QPdfWriter(str(path))
        if not painter.begin(writer):
            raise RuntimeError("Nie można zbudować fikcyjnego PDF")
        painter.drawText(100, 130, "WYŁĄCZNIE TESTOWA FAKTURA")
        painter.end()

    def test_widok_filtrowanie_i_otwarcie_bez_nowego_zapisu(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "syntetyczna.pdf"
            self.fake_pdf(pdf)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "config.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "demo:1"})
                    win = OknoGlowne(db)
                    win.show()
                    self.app.processEvents()
                    table = win.tabela_faktur
                    self.assertEqual(table.tabela.rowCount(), 0)

                    win.otworz_pdf(pdf)
                    document = win.aktualny_dokument_id
                    self.assertEqual(table.tabela.rowCount(), 0)  # import nie jest zapisem
                    win.ed_dostawca.setText("Operator Fikcyjny")
                    win.ed_numer.setText("FV/TEST/2026")
                    win.ed_kwota.setText("140,05")
                    win.wybor_kategoria.setCurrentIndex(1)
                    win.zapisz_przycisk.click()
                    self.assertEqual(table.tabela.rowCount(), 1)
                    self.assertEqual(table.tabela.item(0, 4).text(), "140,05 zł")
                    self.assertIn("140,05", table.podsumowanie.text())

                    win.karty.setCurrentIndex(win.ETAP_FAKTURY)
                    self.assertFalse(win.podglad.isVisible())
                    table.szukaj.setText("nie ma takiej faktury")
                    self.assertTrue(table.tabela.isRowHidden(0))
                    self.assertIn("0/1", table.podsumowanie.text())
                    table.szukaj.setText("fikcyjny")
                    self.assertFalse(table.tabela.isRowHidden(0))
                    table.tabela.selectRow(0)
                    self.assertEqual(table.wybrane_dokument_id(), document)
                    table.btn_otworz.click()
                    self.assertEqual(win.aktualny_dokument_id, document)
                    self.assertEqual(win.karty.currentIndex(), win.ETAP_FAKTURA)
                    self.assertEqual(db.db.execute(
                        "SELECT COUNT(*) FROM rachunki"
                    ).fetchone()[0], 1)

                    win.karty.setCurrentIndex(win.ETAP_FAKTURY)
                    table.filtr_status.setCurrentIndex(2)  # opłacone
                    self.assertTrue(table.tabela.isRowHidden(0))
                    table.filtr_status.setCurrentIndex(0)
                    self.assertFalse(table.tabela.isRowHidden(0))

                    win.change_language("en")
                    self.assertEqual(win.nawigacja.item(win.ETAP_FAKTURY).text(),
                                     "Invoices")
                    self.assertEqual(table.tabela.horizontalHeaderItem(0).text(),
                                     "Supplier")
                    self.assertEqual(table.tabela.item(0, 4).text(), "140,05 PLN")
                    self.assertEqual(table.szukaj.text(), "fikcyjny")
                    win.close()
            finally:
                set_language("pl")
                db.zamknij()


    def test_kwoty_sortuja_sie_liczbowo(self):
        # Niezależność od języka ustawionego przez poprzednie testy.
        set_language("pl")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = RejestrRachunkow(root / "dane")
            try:
                category = int(db.kategorie()[0]["id"])
                for name, amount, number in (
                    ("mala.pdf", "9,00", "TEST/09"),
                    ("duza.pdf", "100,00", "TEST/100"),
                ):
                    pdf = root / name
                    pdf.write_bytes(("%PDF-1.4\n% " + name + "\n%%EOF\n").encode())
                    doc = db.importuj_pdf(pdf)[0]
                    db.zapisz_rachunek(DaneRachunku(
                        dokument_id=doc, dostawca="DEMO", numer=number,
                        kwota=amount, kategoria_id=category,
                    ))
                table = TabelaFaktur(db)
                table.tabela.sortItems(4, Qt.SortOrder.AscendingOrder)
                self.assertEqual(table.tabela.item(0, 4).text(), "9,00 zł")
                self.assertEqual(table.tabela.item(1, 4).text(), "100,00 zł")
                table.tabela.sortItems(4, Qt.SortOrder.DescendingOrder)
                self.assertEqual(table.tabela.item(0, 4).text(), "100,00 zł")
                table.close()
            finally:
                set_language("pl")
                db.zamknij()

    def test_po_nadpisaniu_widoczny_jeden_zaktualizowany_rekord(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "faktura-demo.pdf"
            self.fake_pdf(pdf)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "config.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "demo:1"})
                    win = OknoGlowne(db)
                    win.otworz_pdf(pdf)
                    win.ed_dostawca.setText("Operator Fikcyjny")
                    win.ed_numer.setText("FV/TEST/2026")
                    win.ed_kwota.setText("10,00")
                    win.wybor_kategoria.setCurrentIndex(1)
                    win.zapisz_przycisk.click()
                    ident = db.faktury()[0]["id"]
                    win.ed_kwota.setText("25,00")
                    with patch.object(
                        QMessageBox, "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ):
                        win.zapisz_przycisk.click()
                    self.assertEqual(win.tabela_faktur.tabela.rowCount(), 1)
                    self.assertEqual(db.faktury()[0]["id"], ident)
                    self.assertEqual(win.tabela_faktur.tabela.item(0, 4).text(),
                                     "25,00 zł")
                    win.close()
            finally:
                set_language("pl")
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
