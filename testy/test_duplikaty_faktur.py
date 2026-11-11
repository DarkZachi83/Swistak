# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Ochrona przed powtórnym zapisem — wyłącznie fikcyjne dokumenty i dane."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QMessageBox

import ustawienia
from gui.okno_glowne import OknoGlowne
from uslugi.rachunki import (
    DaneRachunku, FakturaJuzIstnieje, RejestrRachunkow,
)


class TestDuplikatyWBazie(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = RejestrRachunkow(self.root / "dane")
        self.category = int(self.db.kategorie()[0]["id"])

    def tearDown(self):
        self.db.zamknij()
        self.temp.cleanup()

    def pdf(self, name, payload):
        path = self.root / name
        path.write_bytes(b"%PDF-1.4\n% demo " + payload.encode() + b"\n%%EOF\n")
        return self.db.importuj_pdf(path)[0]

    def data(self, doc, *, supplier="Operator DEMO", number="FV/ABC/2026",
             amount="42,00"):
        return DaneRachunku(
            dokument_id=doc, dostawca=supplier, numer=number,
            kwota=amount, kategoria_id=self.category,
            data_wystawienia="2026-11-11",
        )

    def test_ten_sam_dokument_wymaga_zgody(self):
        doc = self.pdf("faktura.pdf", "first")
        pk = self.db.zapisz_rachunek(self.data(doc))
        duplicate = self.db.znajdz_duplikat(self.data(doc, amount="10,00"))
        self.assertEqual(int(duplicate["id"]), pk)
        with self.assertRaises(FakturaJuzIstnieje) as ctx:
            self.db.zapisz_rachunek(self.data(doc, amount="10,00"))
        self.assertEqual(ctx.exception.rachunek_id, pk)
        self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 4200)
        self.assertEqual(self.db.db.execute(
            "SELECT COUNT(*) FROM rachunki"
        ).fetchone()[0], 1)

        updated = self.db.zapisz_rachunek(
            self.data(doc, amount="10,00"), nadpisz_id=pk
        )
        self.assertEqual(updated, pk)
        self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 1000)
        self.assertEqual(self.db.db.execute(
            "SELECT COUNT(*) FROM pozycje_rachunku WHERE rachunek_id=?",
            (pk,),
        ).fetchone()[0], 1)

    def test_inny_pdf_ten_sam_dostawca_numer_to_ta_sama_faktura(self):
        old = self.pdf("oryginal.pdf", "first")
        new = self.pdf("poprawiony.pdf", "second")
        pk = self.db.zapisz_rachunek(self.data(old))
        candidate = self.data(
            new, supplier="  operator   demo  ", number="fv/abc/2026",
            amount="55,50",
        )
        self.assertEqual(self.db.znajdz_duplikat(candidate)["id"], pk)
        original_bytes = self.db.sciezka_pdf(old).read_bytes()
        with self.assertRaises(FakturaJuzIstnieje):
            self.db.zapisz_rachunek(candidate)
        self.assertIsNone(self.db.rachunek(new))
        self.assertEqual(self.db.rachunek(old)["kwota_grosze"], 4200)
        self.assertEqual(self.db.zapisz_rachunek(candidate, nadpisz_id=pk), pk)
        self.assertEqual(self.db.rachunek(new)["kwota_grosze"], 5550)
        self.assertIsNone(self.db.rachunek(old))
        self.assertEqual(self.db.sciezka_pdf(old).read_bytes(), original_bytes)
        self.assertEqual(len(self.db.dokumenty()), 2)
        self.assertEqual(self.db.db.execute(
            "SELECT COUNT(*) FROM rachunki"
        ).fetchone()[0], 1)

    def test_different_invoice_number_or_supplier_is_not_duplicate(self):
        first = self.pdf("a.pdf", "a")
        second = self.pdf("b.pdf", "b")
        third = self.pdf("c.pdf", "c")
        self.db.zapisz_rachunek(self.data(first))
        distinct_number = self.data(second, number="FV/DEF/2026")
        distinct_supplier = self.data(third, supplier="Inny Operator DEMO")
        self.assertIsNone(self.db.znajdz_duplikat(distinct_number))
        self.assertIsNone(self.db.znajdz_duplikat(distinct_supplier))
        self.db.zapisz_rachunek(distinct_number)
        self.db.zapisz_rachunek(distinct_supplier)
        self.assertEqual(self.db.db.execute(
            "SELECT COUNT(*) FROM rachunki"
        ).fetchone()[0], 3)

    def test_brak_numeru_nie_oznacza_ze_wszystkie_rachunki_dostawcy_to_jeden(self):
        a = self.pdf("a.pdf", "a")
        b = self.pdf("b.pdf", "b")
        self.db.zapisz_rachunek(self.data(a, number=""))
        self.assertIsNone(self.db.znajdz_duplikat(self.data(b, number="")))
        self.db.zapisz_rachunek(self.data(b, number=""))
        self.assertEqual(self.db.db.execute(
            "SELECT COUNT(*) FROM rachunki"
        ).fetchone()[0], 2)
        self.assertIsNotNone(self.db.znajdz_duplikat(self.data(a, number="")))

    def test_zla_zgoda_lub_ponowny_zapis_bez_zgody_nie_nadpisuje(self):
        doc = self.pdf("a.pdf", "a")
        first = self.db.zapisz_rachunek(self.data(doc))
        with self.assertRaises(ValueError):
            self.db.zapisz_rachunek(
                self.data(doc, amount="99,99"), nadpisz_id=first + 10
            )
        with self.assertRaises(ValueError):
            self.db.zapisz_rachunek(
                self.data(self.pdf("b.pdf", "b"), number="INNY"),
                nadpisz_id=first,
            )
        self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 4200)


class TestDuplikatWInterfejsie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def make_pdf(path):
        writer = QPdfWriter(str(path))
        painter = QPainter(writer)
        if not painter.isActive():
            raise RuntimeError("Nie udało się utworzyć syntetycznego PDF")
        painter.drawText(95, 120, "Wyłącznie fikcyjna faktura DEMO")
        painter.end()

    def test_nie_zachowuje_baze_tak_zmienia_tylko_jeden_rekord(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "syntetyczna.pdf"
            self.make_pdf(pdf)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "ustawienia.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "test:1"})
                    win = OknoGlowne(db)
                    win.show()
                    self.app.processEvents()
                    win.otworz_pdf(pdf)
                    doc = win.aktualny_dokument_id
                    win.ed_dostawca.setText("Operator DEMO")
                    win.ed_numer.setText("FV/01/2026")
                    win.ed_kwota.setText("42,00")
                    win.wybor_kategoria.setCurrentIndex(1)
                    win.zapisz_przycisk.click()
                    original = db.rachunek(doc)
                    self.assertEqual(original["kwota_grosze"], 4200)
                    pk = original["id"]

                    # Wczytanie tego samego PDF-a nie tworzy nowego dokumentu.
                    win.otworz_pdf(pdf)
                    self.assertEqual(win.aktualny_dokument_id, doc)
                    win.ed_kwota.setText("85,00")
                    with patch.object(
                        QMessageBox, "question",
                        return_value=QMessageBox.StandardButton.No,
                    ) as question:
                        win.zapisz_przycisk.click()
                        question.assert_called_once()
                        args = question.call_args.args
                        self.assertIn("już w bazie", args[1])
                        self.assertIn("Czy nadpisać", args[2])
                        self.assertEqual(args[-1], QMessageBox.StandardButton.No)

                    self.assertEqual(db.rachunek(doc)["kwota_grosze"], 4200)
                    self.assertEqual(db.db.execute(
                        "SELECT COUNT(*) FROM rachunki"
                    ).fetchone()[0], 1)
                    self.assertEqual(win.ed_kwota.text(), "85,00")

                    with patch.object(
                        QMessageBox, "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ) as question:
                        win.zapisz_przycisk.click()
                        question.assert_called_once()
                    self.assertEqual(db.rachunek(doc)["id"], pk)
                    self.assertEqual(db.rachunek(doc)["kwota_grosze"], 8500)
                    self.assertEqual(db.db.execute(
                        "SELECT COUNT(*) FROM rachunki"
                    ).fetchone()[0], 1)
                    win.close()
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
