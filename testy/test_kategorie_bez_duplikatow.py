# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bezpieczna konsolidacja kategorii: tylko syntetyczne rachunki."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uslugi.kategorie import klucz_kategorii, podobne_kategorie
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class TestBezpieczneKategorie(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = RejestrRachunkow(self.root / "dane")

    def tearDown(self):
        self.db.zamknij()
        self.temp.cleanup()

    def test_proponuje_poprawna_kategorie_zamiast_literowki(self):
        self.assertEqual(
            klucz_kategorii(" ENERGIA— elektryczna  "),
            klucz_kategorii("energia elektryczna"),
        )
        self.assertIn("Energia elektryczna", podobne_kategorie(
            "Energi", [r["nazwa"] for r in self.db.kategorie()]
        ))
        with self.assertRaisesRegex(ValueError, "podobne"):
            self.db.dodaj_kategorie("Energi")
        with self.assertRaisesRegex(ValueError, "już istnieje"):
            self.db.dodaj_kategorie("Energia–elektryczna",
                                   zezwol_na_podobna=True)
        self.assertEqual(len(self.db.kategorie()), 6)

    def test_swiadome_utworzenie_podobnej_kategorii_jest_mozliwe(self):
        ident = self.db.dodaj_kategorie("Energia cieplna",
                                      zezwol_na_podobna=True)
        self.assertIn(ident, [int(r["id"]) for r in self.db.kategorie()])
        with self.assertRaises(ValueError):
            self.db.dodaj_kategorie("Energia cieplna",
                                   zezwol_na_podobna=True)
        self.assertEqual(len(self.db.kategorie()), 7)

    def _zapisz_fikcyjna(self, name: str, kat: int, number: str) -> tuple[int, bytes]:
        path = self.root / name
        data = ("%PDF-1.4\n% TYLKO SYNTHETIC " + name + "\n%%EOF\n").encode()
        path.write_bytes(data)
        doc, _ = self.db.importuj_pdf(path)
        rachunek_id = self.db.zapisz_rachunek(DaneRachunku(
            dokument_id=doc, dostawca="Firma Testowa",
            numer=number, kwota="125,55", kategoria_id=kat
        ))
        return rachunek_id, data

    def test_scalanie_zachowuje_faktury_kwoty_pdf_i_integralnosc(self):
        source = self.db.dodaj_kategorie("Energi", zezwol_na_podobna=True)
        target = next(int(r["id"]) for r in self.db.kategorie()
                      if r["nazwa"] == "Energia elektryczna")
        rachunek, bytes_before = self._zapisz_fikcyjna(
            "faktura-a.pdf", source, "DEMO/A"
        )
        self._zapisz_fikcyjna("faktura-b.pdf", target, "DEMO/B")
        before = self.db.db.execute(
            "SELECT SUM(kwota_grosze), COUNT(*) FROM rachunki"
        ).fetchone()
        self.assertEqual(self.db.scal_kategorie(source, target), 1)
        after = self.db.db.execute(
            "SELECT SUM(kwota_grosze), COUNT(*) FROM rachunki"
        ).fetchone()
        self.assertEqual(tuple(before), tuple(after))
        self.assertEqual(self.db.db.execute(
            "SELECT kategoria_id FROM pozycje_rachunku WHERE rachunek_id = ?",
            (rachunek,)
        ).fetchone()[0], target)
        self.assertEqual(self.db.db.execute(
            "SELECT COUNT(*) FROM pozycje_rachunku WHERE kategoria_id = ?",
            (target,)
        ).fetchone()[0], 2)
        self.assertEqual(self.db.db.execute(
            "SELECT aktywna FROM kategorie WHERE id = ?", (source,)
        ).fetchone()[0], 0)
        self.assertNotIn(source, [r["id"] for r in self.db.kategorie()])
        self.assertEqual(self.db.sciezka_pdf(
            self.db.db.execute("SELECT dokument_id FROM rachunki WHERE id = ?",
                               (rachunek,)).fetchone()[0]
        ).read_bytes(), bytes_before)

    def test_bledne_scalanie_nic_nie_zmienia(self):
        source = self.db.dodaj_kategorie("Energi", zezwol_na_podobna=True)
        target = next(int(r["id"]) for r in self.db.kategorie()
                      if r["nazwa"] == "Energia elektryczna")
        with self.assertRaises(ValueError):
            self.db.scal_kategorie(target, source)  # kategoria podstawowa
        with self.assertRaises(ValueError):
            self.db.scal_kategorie(source, source)
        with self.assertRaises(ValueError):
            self.db.scal_kategorie(source, 999999)
        self.assertEqual(self.db.db.execute(
            "SELECT aktywna FROM kategorie WHERE id = ?", (source,)
        ).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
