# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Czyszczenie danych: tylko fikcyjne SQLite, PDF-y i wzorce."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from uslugi.czyszczenie_bazy import (
    BladCzyszczenia, podmien_na_pusta, przygotuj_pusta_baze,
    usun_poprzednie_dane,
)
from uslugi.kopie_zapasowe import (
    cofnij_podmiane, przygotuj_przywracanie, utworz_kopie,
)
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class TestCzyszczenieBazy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.root = self.home / "dane"
        self.reg = RejestrRachunkow(self.root)

    def tearDown(self):
        self.reg.zamknij()
        self.tmp.cleanup()

    def _seed(self):
        file = self.home / "wymyslona.pdf"
        file.write_bytes(b"%PDF-1.4\n% TYLKO SYNTHETIC PDF\n%%EOF\n")
        doc_id, _ = self.reg.importuj_pdf(file)
        category = int(self.reg.kategorie()[0]["id"])
        self.reg.zapisz_rachunek(DaneRachunku(
            dokument_id=doc_id, dostawca="Fikcyjna spolka",
            numer="DEMO/1", kwota="10,00", kategoria_id=category,
        ))
        self.reg.dodaj_kategorie("Demonstracyjna")
        folder = self.root / "wzorce"
        folder.mkdir(exist_ok=True)
        (folder / "syntetyczny.json").write_text('{"fake":true}')
        return doc_id

    def test_pusta_baza_zamiast_starej_a_kopia_pozostaje(self):
        doc_id = self._seed()
        saved_pdf = self.reg.sciezka_pdf(doc_id).read_bytes()
        zip_path = self.home / "prywatna-kopia.zip"
        utworz_kopie(self.reg, zip_path)
        verified = przygotuj_przywracanie(zip_path, self.root)
        verified.sprzataj()
        stage = przygotuj_pusta_baze(self.root)
        self.assertEqual(self.reg.rachunek(doc_id)["kwota_grosze"], 1000)
        self.reg.zamknij()
        previous = podmien_na_pusta(self.root, stage)
        self.reg.__init__(self.root)
        self.assertEqual(self.reg.db.execute("SELECT COUNT(*) FROM dokumenty").fetchone()[0], 0)
        self.assertEqual(self.reg.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 0)
        self.assertEqual(len(self.reg.kategorie()), 6)
        self.assertEqual(list((self.root / "dokumenty").rglob("*.pdf")), [])
        self.assertFalse((self.root / "wzorce").exists())
        self.assertEqual(next((previous / "dokumenty").rglob("*.pdf")).read_bytes(), saved_pdf)
        usun_poprzednie_dane(previous, self.root)
        self.assertFalse(previous.exists())
        self.assertTrue(zip_path.exists())
        restored = przygotuj_przywracanie(zip_path, self.root)
        try:
            self.assertEqual(restored.opis.dokumenty_pdf, 1)
        finally:
            restored.sprzataj()

    def test_cudzy_plik_w_katalogu_blokuje_usuwanie(self):
        self._seed()
        foreign = self.root / "notatki.txt"
        foreign.write_text("nie ruszaj")
        with self.assertRaises(BladCzyszczenia):
            przygotuj_pusta_baze(self.root)
        self.assertEqual(foreign.read_text(), "nie ruszaj")
        self.assertEqual(self.reg.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 1)

    def test_awaria_podmiany_przywraca_stara_baze(self):
        doc_id = self._seed()
        stage = przygotuj_pusta_baze(self.root)
        self.reg.zamknij()
        from uslugi.czyszczenie_bazy import os as wiping_os
        original_replace = wiping_os.replace

        def fail_second_move(src, dst):
            if Path(src) == stage:
                raise OSError("fikcyjna awaria drugiego przeniesienia")
            return original_replace(src, dst)

        with patch("uslugi.czyszczenie_bazy.os.replace", side_effect=fail_second_move):
            with self.assertRaises(OSError):
                podmien_na_pusta(self.root, stage)
        self.reg.__init__(self.root)
        self.assertEqual(self.reg.rachunek(doc_id)["kwota_grosze"], 1000)
        self.assertEqual(self.reg.db.execute("SELECT COUNT(*) FROM dokumenty").fetchone()[0], 1)

    def test_przerwane_czyszczenie_nie_tworzy_pustej_bazy(self):
        missing = self.home / "inny-katalog"
        previous = self.home / "inny-katalog-przed-wyczyszczeniem-20261112-010101"
        previous.mkdir()
        with self.assertRaisesRegex(RuntimeError, "przerwane"):
            RejestrRachunkow(missing)
        self.assertFalse(missing.exists())

    def test_cofanie_po_nieudanym_inicjowaniu_nowego_okna(self):
        doc_id = self._seed()
        stage = przygotuj_pusta_baze(self.root)
        self.reg.zamknij()
        previous = podmien_na_pusta(self.root, stage)
        cofnij_podmiane(self.root, previous)
        self.reg.__init__(self.root)
        self.assertEqual(self.reg.rachunek(doc_id)["kwota_grosze"], 1000)


if __name__ == "__main__":
    unittest.main()
