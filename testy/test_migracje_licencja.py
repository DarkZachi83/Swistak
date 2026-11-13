# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Regresja: licencja migracji nie może uniemożliwiać otwarcia starej bazy.

Wszystkie informacje są syntetyczne; test nie czyta danych użytkownika.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from baza.migracje import BladMigracji, zastosuj_migracje
from baza.polaczenie import polacz
from uslugi.rachunki import RejestrRachunkow


SCHEMAT = Path(__file__).resolve().parents[1] / "baza" / "schemat"
STARY = b"-- SPDX-License-Identifier: GPL-3.0-only\n"
NOWY = b"-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0\n"
PLIKI = ("001_start.sql", "002_numer_konta.sql")


def historyczne_migracje(folder: Path, stare: set[str]) -> dict[str, str]:
    folder.mkdir()
    sha = {}
    for nazwa in PLIKI:
        oryginal = (SCHEMAT / nazwa).read_bytes()
        assert oryginal.startswith(NOWY), nazwa
        tresc = STARY + oryginal[len(NOWY):] if nazwa in stare else oryginal
        (folder / nazwa).write_bytes(tresc)
        sha[nazwa] = hashlib.sha256(tresc).hexdigest()
    return sha


class TestZgodnoscHistorycznychMigracji(unittest.TestCase):
    def _starsza_baza(self, root: Path, stare: set[str]):
        bazapath = root / "dane" / "swistak.sqlite3"
        sciezka_migracji = root / "migracje-stare"
        zrodla = historyczne_migracje(sciezka_migracji, stare)
        db = polacz(bazapath)
        try:
            zastosuj_migracje(db, sciezka_migracji)
            db.execute(
                "INSERT INTO dokumenty (nazwa_zrodlowa, sha256, "
                "sciezka_wzgledna, rozmiar_bajtow) "
                "VALUES ('test.pdf', ?, 'dokumenty/ab/test.pdf', 20)",
                ("a" * 64,)
            )
            db.execute(
                "INSERT INTO rachunki (dokument_id, dostawca, kwota_grosze) "
                "VALUES (1, 'Dostawca testowy', 12345)"
            )
        finally:
            db.close()
        return bazapath, zrodla

    def test_baza_wszystkie_migracje_gpl_przetrwa_nowa_licencje(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bazapath, expected = self._starsza_baza(root, set(PLIKI))
            rejestr = RejestrRachunkow(bazapath.parent)
            try:
                self.assertEqual(rejestr.rachunek(1)["kwota_grosze"], 12345)
                self.assertEqual(rejestr.rachunek(1)["dostawca"], "Dostawca testowy")
                recorded = dict(rejestr.db.execute(
                    "SELECT nazwa, sha256 FROM migracje"
                ).fetchall())
                self.assertEqual({k: recorded[k] for k in PLIKI}, expected)
                self.assertTrue(set(recorded) >= set(PLIKI))
            finally:
                rejestr.zamknij()

    def test_baza_z_jednym_historycznym_naglowkiem(self):
        for stare in ({"001_start.sql"}, {"002_numer_konta.sql"}):
            with self.subTest(stare=stare):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    _, expected = self._starsza_baza(root, stare)
                    rejestr = RejestrRachunkow(root / "dane")
                    try:
                        self.assertEqual(rejestr.rachunek(1)["kwota_grosze"], 12345)
                        recorded = dict(rejestr.db.execute(
                            "SELECT nazwa, sha256 FROM migracje"
                        ).fetchall())
                        self.assertEqual({k: recorded[k] for k in PLIKI}, expected)
                    finally:
                        rejestr.zamknij()

    def test_zmiana_sql_jest_wciaz_odrzucana(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bazapath, _ = self._starsza_baza(root, set(PLIKI))
            zly_folder = root / "migracje-zmodyfikowane"
            historyczne_migracje(zly_folder, set())
            with (zly_folder / "001_start.sql").open("ab") as plik:
                plik.write(b"\n-- Nieautoryzowana zmiana SQL / komentarza\n")
            db = polacz(bazapath)
            try:
                with self.assertRaisesRegex(BladMigracji, "001_start.sql"):
                    zastosuj_migracje(db, zly_folder)
                self.assertEqual(db.execute(
                    "SELECT kwota_grosze FROM rachunki WHERE dokument_id=1"
                ).fetchone()[0], 12345)
            finally:
                db.close()

    def test_przyszla_migracja_nie_ma_wyjatku(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sciezka = root / "swistak.sqlite3"
            folder = root / "migracje"
            historyczne_migracje(folder, set())
            plik = folder / "003_test.sql"
            plik.write_bytes(
                b"-- SPDX-License-Identifier: GPL-3.0-only\n"
                b"CREATE TABLE test_migracji (id INTEGER);\n"
            )
            db = polacz(sciezka)
            try:
                zastosuj_migracje(db, folder)
                plik.write_bytes(
                    plik.read_bytes().replace(STARY, NOWY, 1)
                )
                with self.assertRaisesRegex(BladMigracji, "003_test.sql"):
                    zastosuj_migracje(db, folder)
            finally:
                db.close()

    def test_nowoutworzona_baza_nie_wymaga_wyjatku(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rejestr = RejestrRachunkow(root / "dane")
            try:
                for nazwa in PLIKI:
                    current = hashlib.sha256((SCHEMAT / nazwa).read_bytes()).hexdigest()
                    actual = rejestr.db.execute(
                        "SELECT sha256 FROM migracje WHERE nazwa = ?", (nazwa,)
                    ).fetchone()[0]
                    self.assertEqual(actual, current)
            finally:
                rejestr.zamknij()


if __name__ == "__main__":
    unittest.main()
