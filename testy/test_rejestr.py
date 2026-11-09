# SPDX-License-Identifier: GPL-3.0-only
"""Testy archiwum i bazy: wyłącznie syntetyczne dane."""
from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from baza.migracje import BladMigracji, zastosuj_migracje
from uslugi.archiwum import BladArchiwum
from uslugi.rachunki import DaneRachunku, RejestrRachunkow, grosze_na_kwote, kwota_na_grosze


class TestRejestr(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rejestr = RejestrRachunkow(self.root / "dane")
        self.zrodlo = self.root / "test.pdf"
        self.zrodlo.write_bytes(b"%PDF-1.4\nsyntetyczny test - nie prawdziwy rachunek\n%%EOF\n")

    def tearDown(self):
        self.rejestr.zamknij()
        self.tmp.cleanup()

    def dane(self, dokument_id: int, **zmiany):
        wartosci = {
            "dokument_id": dokument_id,
            "dostawca": "Dostawca testowy",
            "numer": "FV/01/2026",
            "kwota": "1234,56",
            "kategoria_id": int(self.rejestr.kategorie()[0]["id"]),
            "data_wystawienia": "2026-11-05",
            "termin_platnosci": "2026-11-15",
            "okres_od": "2026-10-01",
            "okres_do": "2026-10-31",
            "status": "do_zaplaty",
            "uwagi": "Tylko dane testowe",
        }
        wartosci.update(zmiany)
        return DaneRachunku(**wartosci)

    def test_domyslne_kategorie(self):
        nazwy = [wiersz["nazwa"] for wiersz in self.rejestr.kategorie()]
        self.assertEqual(len(nazwy), 6)
        self.assertIn("Fundusz remontowy", nazwy)
        self.assertIn("Energia elektryczna", nazwy)

    def test_import_zachowuje_bajty_i_zrodlo(self):
        bajty = self.zrodlo.read_bytes()
        identyfikator, nowy = self.rejestr.importuj_pdf(self.zrodlo)
        self.assertTrue(nowy)
        self.assertEqual(self.zrodlo.read_bytes(), bajty)
        self.assertEqual(self.rejestr.sciezka_pdf(identyfikator).read_bytes(), bajty)
        self.assertEqual(self.rejestr.dokument(identyfikator)["sha256"],
                         hashlib.sha256(bajty).hexdigest())
        self.assertNotEqual(self.zrodlo.resolve(), self.rejestr.sciezka_pdf(identyfikator))

    def test_duplikat_pod_inna_nazwa(self):
        pierwszy, nowy = self.rejestr.importuj_pdf(self.zrodlo)
        self.assertTrue(nowy)
        inna = self.root / "innanazwa.PDF"
        inna.write_bytes(self.zrodlo.read_bytes())
        drugi, nowy = self.rejestr.importuj_pdf(inna)
        self.assertEqual(pierwszy, drugi)
        self.assertFalse(nowy)
        self.assertEqual(len(self.rejestr.dokumenty()), 1)
        self.assertEqual(len(list((self.root / "dane" / "dokumenty").rglob("*.pdf"))), 1)

    def test_rozne_pliki_rozne_id(self):
        a, _ = self.rejestr.importuj_pdf(self.zrodlo)
        inna = self.root / "inna.pdf"
        inna.write_bytes(b"%PDF-1.4\ninny syntetyczny dokument\n%%EOF\n")
        b, nowy = self.rejestr.importuj_pdf(inna)
        self.assertTrue(nowy)
        self.assertNotEqual(a, b)

    def test_odrzuca_nie_pdf_i_zly_podpis(self):
        brak = self.root / "nieistnieje.pdf"
        with self.assertRaises(BladArchiwum):
            self.rejestr.importuj_pdf(brak)
        zly = self.root / "zly.pdf"
        zly.write_bytes(b"nie jest to pdf")
        with self.assertRaises(BladArchiwum):
            self.rejestr.importuj_pdf(zly)
        self.assertEqual(len(self.rejestr.dokumenty()), 0)

    def test_naruszony_plik_w_archiwum(self):
        identyfikator, _ = self.rejestr.importuj_pdf(self.zrodlo)
        arch = self.rejestr.sciezka_pdf(identyfikator)
        arch.write_bytes(b"%PDF-1.4\nzawartosc zmieniona!\n")
        with self.assertRaises(BladArchiwum):
            self.rejestr.sciezka_pdf(identyfikator)
        with self.assertRaises(BladArchiwum):
            self.rejestr.importuj_pdf(self.zrodlo)

    def test_sciezka_nie_moze_wyjsc_z_magazynu(self):
        with self.assertRaises(BladArchiwum):
            self.rejestr.magazyn.sciezka("../poufne.pdf")
        with self.assertRaises(BladArchiwum):
            self.rejestr.magazyn.sciezka(str(self.zrodlo.resolve()))

    def test_zapis_i_odczyt_rachunku(self):
        identyfikator, _ = self.rejestr.importuj_pdf(self.zrodlo)
        rachunek_id = self.rejestr.zapisz_rachunek(self.dane(identyfikator))
        wiersz = self.rejestr.rachunek(identyfikator)
        self.assertEqual(wiersz["id"], rachunek_id)
        self.assertEqual(wiersz["kwota_grosze"], 123456)
        self.assertEqual(wiersz["status"], "do_zaplaty")
        self.assertEqual(wiersz["okres_od"], "2026-10-01")
        self.assertEqual(self.rejestr.db.execute(
            "SELECT COUNT(*) FROM pozycje_rachunku WHERE rachunek_id = ?",
            (rachunek_id,)).fetchone()[0], 1)
        self.assertEqual(self.rejestr.db.execute(
            "SELECT SUM(kwota_grosze) FROM pozycje_rachunku WHERE rachunek_id = ?",
            (rachunek_id,)).fetchone()[0], 123456)

    def test_edycja_nie_duplikuje_pozycji(self):
        dokument_id, _ = self.rejestr.importuj_pdf(self.zrodlo)
        pierwszy = self.rejestr.zapisz_rachunek(self.dane(dokument_id))
        drugi = self.rejestr.zapisz_rachunek(self.dane(
            dokument_id, kwota="12,34", status="oplacony",
        ))
        self.assertEqual(pierwszy, drugi)
        self.assertEqual(self.rejestr.rachunek(dokument_id)["kwota_grosze"], 1234)
        self.assertEqual(self.rejestr.rachunek(dokument_id)["status"], "oplacony")
        self.assertEqual(self.rejestr.db.execute(
            "SELECT COUNT(*) FROM pozycje_rachunku WHERE rachunek_id = ?",
            (pierwszy,)).fetchone()[0], 1)

    def test_zapis_przetrwa_restart(self):
        dokument_id, _ = self.rejestr.importuj_pdf(self.zrodlo)
        self.rejestr.zapisz_rachunek(self.dane(dokument_id))
        self.rejestr.zamknij()
        self.rejestr = RejestrRachunkow(self.root / "dane")
        self.assertEqual(self.rejestr.rachunek(dokument_id)["kwota_grosze"], 123456)
        self.assertTrue(self.rejestr.sciezka_pdf(dokument_id).is_file())

    def test_nieprawidlowa_data_nie_zapisuje(self):
        dokument_id, _ = self.rejestr.importuj_pdf(self.zrodlo)
        with self.assertRaises(ValueError):
            self.rejestr.zapisz_rachunek(self.dane(
                dokument_id, data_wystawienia="2026-02-30",
            ))
        self.assertIsNone(self.rejestr.rachunek(dokument_id))
        with self.assertRaises(ValueError):
            self.rejestr.zapisz_rachunek(self.dane(
                dokument_id, okres_od="2026-11-05", okres_do="2026-10-01",
            ))

    def test_nieprawidlowy_status_lub_kategoria(self):
        dokument_id, _ = self.rejestr.importuj_pdf(self.zrodlo)
        for zmiana in ({"status": "dowolny"}, {"kategoria_id": 99999}):
            with self.assertRaises(ValueError):
                self.rejestr.zapisz_rachunek(self.dane(dokument_id, **zmiana))
        self.assertIsNone(self.rejestr.rachunek(dokument_id))

    def test_rollback_przy_bledzie_w_srodku_zapisu(self):
        dokument_id, _ = self.rejestr.importuj_pdf(self.zrodlo)
        self.rejestr.zapisz_rachunek(self.dane(dokument_id))
        self.rejestr.db.execute(
            "CREATE TRIGGER nie_pozwalaj AFTER DELETE ON pozycje_rachunku "
            "BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.rejestr.zapisz_rachunek(self.dane(dokument_id, kwota="5"))
        self.assertEqual(self.rejestr.rachunek(dokument_id)["kwota_grosze"], 123456)

    def test_dodaj_kategorie_i_odrzuc_powtorke(self):
        identyfikator = self.rejestr.dodaj_kategorie("  Wywóz   odpadów ")
        self.assertIn(identyfikator, [x["id"] for x in self.rejestr.kategorie()])
        with self.assertRaises(ValueError):
            self.rejestr.dodaj_kategorie("Wywóz odpadów")
        with self.assertRaises(ValueError):
            self.rejestr.dodaj_kategorie(" ")

    def test_integralnosc_kluczy_obcych(self):
        self.assertEqual(self.rejestr.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.rejestr.db.execute(
                "INSERT INTO pozycje_rachunku (rachunek_id, kategoria_id, kwota_grosze) "
                "VALUES (99999, 99999, 100)"
            )

    def test_weryfikacja_niezmiennosci_migracji(self):
        folder = self.root / "testowe_migracje"
        folder.mkdir()
        oryginal = Path(__file__).parents[1] / "baza" / "schemat" / "001_start.sql"
        (folder / oryginal.name).write_bytes(oryginal.read_bytes() + b"\n-- komentarz")
        with self.assertRaises(BladMigracji):
            zastosuj_migracje(self.rejestr.db, folder)
        self.assertEqual(len(self.rejestr.kategorie()), 6)

    def test_nieznana_migracja_nie_niszczy_bazy(self):
        folder = self.root / "puste_migracje"
        folder.mkdir()
        (folder / "002_nowa.sql").write_text("SELECT 1;\n", encoding="utf-8")
        with self.assertRaises(BladMigracji):
            zastosuj_migracje(self.rejestr.db, folder)
        self.assertEqual(len(self.rejestr.kategorie()), 6)

    def test_rollback_nieudanej_nowej_migracji(self):
        folder = self.root / "kolejne"
        folder.mkdir()
        oryginal = Path(__file__).parents[1] / "baza" / "schemat" / "001_start.sql"
        (folder / oryginal.name).write_bytes(oryginal.read_bytes())
        (folder / "002_blad.sql").write_text(
            "CREATE TABLE testowa_tmp (id INTEGER);\n"
            "INSERT INTO brakujaca_tabela VALUES (1);\n", encoding="utf-8"
        )
        with self.assertRaises(BladMigracji):
            zastosuj_migracje(self.rejestr.db, folder)
        self.assertIsNone(self.rejestr.db.execute(
            "SELECT name FROM sqlite_master WHERE name='testowa_tmp'"
        ).fetchone())
        self.assertIsNone(self.rejestr.db.execute(
            "SELECT 1 FROM migracje WHERE nazwa='002_blad.sql'"
        ).fetchone())


class TestKwoty(unittest.TestCase):
    def test_prawidlowa_kwota(self):
        for wartosc, oczekiwana in (
            ("1 234,56", 123456), ("1\u00a0234,56", 123456),
            ("0", 0), ("2.4", 240), ("2,40", 240),
        ):
            with self.subTest(wartosc=wartosc):
                self.assertEqual(kwota_na_grosze(wartosc), oczekiwana)
        self.assertEqual(grosze_na_kwote(123456), "1234,56")

    def test_kwota_bledna(self):
        for wartosc in ("", "-1", "12,345", "NaN", "1e3", "1,2,3", "1.000,00"):
            with self.subTest(wartosc=wartosc):
                with self.assertRaises(ValueError):
                    kwota_na_grosze(wartosc)


if __name__ == "__main__":
    unittest.main()
