# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Szybkie testy duplikatów SQLite bez zależności Qt i prywatnych faktur."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uslugi.rachunki import DaneRachunku, FakturaJuzIstnieje, RejestrRachunkow


class TestZabezpieczenieFaktury(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = RejestrRachunkow(self.root / "dane")
        self.category = int(self.db.kategorie()[0]["id"])

    def tearDown(self):
        self.db.zamknij()
        self.tmp.cleanup()

    def pdf(self, name: str, text: str):
        source = self.root / name
        source.write_bytes(b"%PDF-1.4\n" + text.encode("utf-8") + b"\n%%EOF\n")
        return self.db.importuj_pdf(source)[0]

    def form(self, doc: int, *, supplier="Testowy Operator", number="FAK/11/2026",
             amount="25,00"):
        return DaneRachunku(
            dokument_id=doc, dostawca=supplier, numer=number, kwota=amount,
            kategoria_id=self.category,
        )

    def test_ponowny_zapis_odmowa_nie_zmienia_danych(self):
        doc = self.pdf("a.pdf", "faktura testowa a")
        pk = self.db.zapisz_rachunek(self.form(doc))
        self.assertEqual(self.db.znajdz_duplikat(self.form(doc))["id"], pk)
        with self.assertRaises(FakturaJuzIstnieje):
            self.db.zapisz_rachunek(self.form(doc, amount="99,00"))
        self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 2500)
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 1)
        self.assertEqual(self.db.db.execute(
            "SELECT COUNT(*) FROM pozycje_rachunku WHERE rachunek_id=?", (pk,)
        ).fetchone()[0], 1)

    def test_zgoda_nadpisuje_zamiast_dodawac(self):
        doc = self.pdf("a.pdf", "faktura testowa a")
        pk = self.db.zapisz_rachunek(self.form(doc))
        new_pk = self.db.zapisz_rachunek(self.form(doc, amount="34,00"), nadpisz_id=pk)
        self.assertEqual(pk, new_pk)
        self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 3400)
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 1)

    def test_zmieniony_pdf_ten_sam_numer_przenosi_powiazanie_po_zgodzie(self):
        a = self.pdf("a.pdf", "faktura testowa a")
        b = self.pdf("b.pdf", "faktura testowa b")
        original_bytes = self.db.sciezka_pdf(a).read_bytes()
        pk = self.db.zapisz_rachunek(self.form(a))
        candidate = self.form(b, supplier="  testowy   operator  ",
                              number="fak/11/2026", amount="44,00")
        self.assertEqual(self.db.znajdz_duplikat(candidate)["id"], pk)
        with self.assertRaises(FakturaJuzIstnieje):
            self.db.zapisz_rachunek(candidate)
        self.assertIsNone(self.db.rachunek(b))
        self.assertEqual(self.db.zapisz_rachunek(candidate, nadpisz_id=pk), pk)
        self.assertIsNone(self.db.rachunek(a))
        self.assertEqual(self.db.rachunek(b)["kwota_grosze"], 4400)
        self.assertEqual(self.db.sciezka_pdf(a).read_bytes(), original_bytes)

    def test_nowe_numery_i_dostawcy_moga_miec_odrebne_faktury(self):
        a = self.pdf("a.pdf", "faktura testowa a")
        b = self.pdf("b.pdf", "faktura testowa b")
        c = self.pdf("c.pdf", "faktura testowa c")
        self.db.zapisz_rachunek(self.form(a))
        self.assertIsNone(self.db.znajdz_duplikat(self.form(b, number="FAK/12/2026")))
        self.assertIsNone(self.db.znajdz_duplikat(self.form(c, supplier="Inny dostawca")))
        self.db.zapisz_rachunek(self.form(b, number="FAK/12/2026"))
        self.db.zapisz_rachunek(self.form(c, supplier="Inny dostawca"))
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 3)

    def test_bez_numeru_ta_sama_firma_moze_wystawic_wiele_faktur(self):
        a = self.pdf("a.pdf", "faktura testowa a")
        b = self.pdf("b.pdf", "faktura testowa b")
        self.db.zapisz_rachunek(self.form(a, number=""))
        self.assertIsNone(self.db.znajdz_duplikat(self.form(b, number="")))
        self.db.zapisz_rachunek(self.form(b, number=""))
        self.assertEqual(self.db.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 2)

    def test_potwierdzenie_obcego_rekordu_jest_odrzucane(self):
        a = self.pdf("a.pdf", "faktura testowa a")
        pk = self.db.zapisz_rachunek(self.form(a))
        with self.assertRaises(ValueError):
            self.db.zapisz_rachunek(self.form(a, amount="77,00"), nadpisz_id=pk + 100)
        self.assertEqual(self.db.rachunek(a)["kwota_grosze"], 2500)


if __name__ == "__main__":
    unittest.main()
