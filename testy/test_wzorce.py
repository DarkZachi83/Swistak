# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Wzorce — tylko dane fikcyjne, nigdy dokumenty użytkownika."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uslugi.dopasowanie_wzorca import (
    cechy_dokumentu, dopasuj, normalizuj_nip, zaproponuj_wzorzec,
)
from uslugi.wzorce import MagazynWzorcow, nowy_wzorzec, zatwierdz_strukture


NIP_DEMO = "1234563218"  # testowo poprawna suma kontrolna, fikcyjny sprzedawca
NIP_INNY = "1234563224"
TEKST = (
    "Faktura nr DEMO/2026/11\n"
    "Sprzedawca:\nOperator Internetowy DEMO\nNIP 123-456-32-18\n"
    "Nabywca:\nKlient Przykładowy\nNIP 123-456-32-24\n"
    "Data wystawienia: 10.11.2026\n"
    "Termin płatności: 20.11.2026\n"
    "Konto bankowe: wartość testowa z pominiętym kontem\n"
    "Wartość faktury: 42,00 PLN\n"
)


def kandydat():
    return zaproponuj_wzorzec(
        TEKST, "Operator Internetowy DEMO", "Internet",
        {"termin_platnosci": "Odczytaj datę z nagłówka."},
        "Nie myl numeru klienta z numerem faktury.",
    )


class TestMagazynWzorcow(unittest.TestCase):
    def test_json_lokalny_wersjonowany_i_przywracany(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "prywatne-dane"
            store = MagazynWzorcow(local)
            self.assertEqual(store.lista(), [])
            item = store.utworz(kandydat())
            path = local / "wzorce" / f"{item['template_id']}.json"
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.pobierz(item["template_id"])["revision"], 1)
            self.assertEqual(len(store.lista(tylko_aktywne=True)), 1)
            serial = path.read_text(encoding="utf-8")
            self.assertNotIn("Klient Przykładowy", serial)
            self.assertNotIn("42,00", serial)
            self.assertNotIn("DEMO/2026/11", serial)
            self.assertNotIn("123-456-32-24", serial)
            self.assertIn("termin_platnosci", serial)
            self.assertIn("Internet", serial)

            changed = store.pobierz(item["template_id"])
            changed["agent_notes"] = ["W nowym układzie daty są po lewej."]
            saved = store.aktualizuj(item["template_id"], changed, expected_revision=1)
            self.assertEqual(saved["revision"], 2)
            archive = local / "wzorce" / "historia" / f"{item['template_id']}.rev-000001.json"
            self.assertTrue(archive.is_file())
            self.assertEqual(store.pobierz(item["template_id"])["revision"], 2)

            with self.assertRaises(ValueError):
                store.aktualizuj(item["template_id"], changed, expected_revision=1)
            restored = store.przywroc(item["template_id"], 1, expected_revision=2)
            self.assertEqual(restored["revision"], 3)
            self.assertIn("Nie myl numeru klienta", restored["agent_notes"][0])
            inactive = store.dezaktywuj(item["template_id"], expected_revision=3)
            self.assertEqual(inactive["status"], "inactive")
            self.assertEqual(store.lista(tylko_aktywne=True), [])
            self.assertEqual(len(store.lista()), 1)

    def test_nie_przyjmuje_surowych_danych_rachunku(self):
        data = kandydat()
        data["buyer_name"] = "WYŁĄCZNIE SYNTETYCZNE"
        with self.assertRaises(ValueError):
            zatwierdz_strukture(data)
        data = kandydat()
        data["agent_notes"] = ["Wpisz na sztywno rachunek 12 3456 7890 1234 5678 9012 3456"]
        with self.assertRaises(ValueError):
            zatwierdz_strukture(data)
        data = kandydat()
        data["fields"]["kwota_do_zaplaty"]["value"] = "42,00"
        with self.assertRaises(ValueError):
            zatwierdz_strukture(data)

    def test_zabroniony_path_i_zly_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MagazynWzorcow(Path(tmp))
            with self.assertRaises(ValueError):
                store.pobierz("../backup")
            original = store.utworz(kandydat())
            path = store.katalog / f"{original['template_id']}.json"
            path.write_text("{ niepoprawny json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                store.lista()


class TestDopasowanieWzorca(unittest.TestCase):
    def test_nip_tylko_sprzedawcy(self):
        self.assertEqual(normalizuj_nip(NIP_DEMO), NIP_DEMO)
        self.assertEqual(normalizuj_nip(NIP_INNY), NIP_INNY)
        self.assertIsNone(normalizuj_nip("0000000000"))
        self.assertIsNone(normalizuj_nip("1234563217"))
        self.assertEqual(cechy_dokumentu(TEKST)["seller_nip"], NIP_DEMO)

    def test_pelne_automatyczne_i_konkurencja(self):
        template = kandydat()
        chosen = dopasuj(TEKST, [template])
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.punkty, 100)
        self.assertEqual(chosen.poziom, "automatic")
        other = kandydat()
        second = dopasuj(TEKST, [template, other])
        self.assertEqual(second.poziom, "suggest")

    def test_inny_nip_nie_moze_dopasowac_mimo_nazwy(self):
        wrong = kandydat()
        wrong["identification"]["seller_nip"] = NIP_INNY
        self.assertIsNone(dopasuj(TEKST, [wrong]))

    def test_ten_sam_nip_i_nazwa_ale_inny_uklad_wymaga_zgody(self):
        same_vendor_other_layout = (
            "Sprzedawca:\nOperator Internetowy DEMO\nNIP 123-456-32-18\n"
            "Nabywca:\nKlient WYŁĄCZNIE TESTOWY\n"
            "Jednorazowy dokument bez typowych etykiet faktury"
        )
        result = dopasuj(same_vendor_other_layout, [kandydat()])
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.punkty, 80)
        self.assertLess(result.punkty, 90)  # zwykła etykieta Sprzedawca to za mało
        self.assertEqual(result.poziom, "suggest")

    def test_brak_nip_moze_tylko_sugerowac(self):
        bez_nipu = TEKST.replace("NIP 123-456-32-18", "NIP nieczytelny")
        result = dopasuj(bez_nipu, [kandydat()])
        self.assertIsNotNone(result)
        self.assertEqual(result.poziom, "suggest")
        # NIP nabywcy nie jest automatyczną wskazówką dostawcy.
        bez_sekcji = TEKST.replace("Sprzedawca:", "Dostawca:")
        self.assertIsNone(cechy_dokumentu(bez_sekcji)["seller_nip"])

    def test_dane_nabywcy_nie_wchodza_do_regul(self):
        data = kandydat()
        self.assertEqual(data["identification"]["seller_nip"], NIP_DEMO)
        self.assertNotIn("Klient Przykładowy", json.dumps(data))
        self.assertFalse("42,00" in json.dumps(data))


if __name__ == "__main__":
    unittest.main()
