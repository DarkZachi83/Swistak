# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Lista zapisanych faktur w SQLite; tylko fikcyjne dane i dokumenty."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class TestRejestrFaktur(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = RejestrRachunkow(self.root / "dane")
        self.cat = int(self.db.kategorie()[0]["id"])

    def tearDown(self):
        self.db.zamknij()
        self.temp.cleanup()

    def pdf(self, filename: str, marker: str) -> int:
        path = self.root / filename
        path.write_bytes(("%PDF-1.4\n% FAKE " + marker + "\n%%EOF\n").encode())
        return self.db.importuj_pdf(path)[0]

    def invoice(self, document: int, *, number: str = "FAKE/11/2026",
                amount: str = "12,34", status: str = "do_zaplaty") -> DaneRachunku:
        return DaneRachunku(
            dokument_id=document, dostawca="Operator Fikcyjny", numer=number,
            kwota=amount, kategoria_id=self.cat, status=status,
            data_wystawienia="2026-11-05", termin_platnosci="2026-11-20",
        )

    def test_pusty_rejestr_i_niezapisany_pdf(self):
        self.assertEqual(self.db.faktury(), [])
        self.pdf("niezapisany.pdf", "jedyny")
        self.assertEqual(self.db.faktury(), [])

    def test_tabela_zwraca_wlasciwe_pola_jedna_pozycja_na_fakture(self):
        first = self.pdf("jeden.pdf", "pierwszy")
        second = self.pdf("dwa.pdf", "drugi")
        ident = self.db.zapisz_rachunek(self.invoice(first))
        self.db.zapisz_rachunek(self.invoice(
            second, number="FAKE/12/2026", amount="210,05", status="oplacony"
        ))
        rows = self.db.faktury()
        self.assertEqual(len(rows), 2)
        latest, earlier = rows
        self.assertEqual(latest["nazwa_zrodlowa"], "dwa.pdf")
        self.assertEqual(latest["kwota_grosze"], 21005)
        self.assertEqual(latest["status"], "oplacony")
        self.assertEqual(earlier["id"], ident)
        self.assertEqual(earlier["dokument_id"], first)
        self.assertEqual(earlier["numer"], "FAKE/11/2026")
        self.assertEqual(earlier["data_wystawienia"], "2026-11-05")
        self.assertEqual(earlier["termin_platnosci"], "2026-11-20")
        self.assertTrue(earlier["kategoria"])

    def test_nadpisanie_odswieza_wiersz_i_powiazany_pdf(self):
        first = self.pdf("oryginal.pdf", "pierwszy")
        second = self.pdf("korekta.pdf", "drugi")
        ident = self.db.zapisz_rachunek(self.invoice(first))
        self.db.zapisz_rachunek(
            self.invoice(second, amount="99,99", status="oplacony"),
            nadpisz_id=ident,
        )
        rows = self.db.faktury()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], ident)
        self.assertEqual(rows[0]["dokument_id"], second)
        self.assertEqual(rows[0]["nazwa_zrodlowa"], "korekta.pdf")
        self.assertEqual(rows[0]["kwota_grosze"], 9999)
        self.assertEqual(rows[0]["status"], "oplacony")
        self.assertEqual(len(self.db.dokumenty()), 2)


if __name__ == "__main__":
    unittest.main()
