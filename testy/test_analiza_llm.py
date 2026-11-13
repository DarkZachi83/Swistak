# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""AI nie księguje nic samodzielnie; testy wyłącznie na syntetycznych danych."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from baza.migracje import zastosuj_migracje
from baza.polaczenie import polacz
from uslugi.analiza_llm import POLA, AnalizaModelu, OcenaPola, analizuj_lokalnie, ocena_json, schemat_json
from uslugi.rachunki import DaneRachunku, RejestrRachunkow
from uslugi.walidacja import poprawny_iban, zweryfikuj_numer_konta


KONTO = "PL61109010140000071219812874"  # poprawny NRB/IBAN użyty wyłącznie w testach
DANE = (
    "FAKTURA TESTOWA\n"
    "Sprzedawca: Zakład Gazowy DEMO\n"
    "Numer faktury: TEST/10/2026\n"
    "Kwota do zapłaty: 189,50 PLN\n"
    "Termin płatności: 2026-12-01\n"
    f"Rachunek bankowy: {KONTO}\n"
    "Usługa: dostawa gazu\n"
)
KATEGORIE = ["Gaz", "Energia elektryczna", "Inne"]


def odpowiedz_demo():
    wynik = {p: {"wartosc": None, "dowod": None} for p in POLA}
    wynik.update({
        "dostawca": {"wartosc": "Zakład Gazowy DEMO",
                      "dowod": "Sprzedawca: Zakład Gazowy DEMO"},
        "numer_faktury": {"wartosc": "TEST/10/2026",
                          "dowod": "Numer faktury: TEST/10/2026"},
        "kwota_do_zaplaty": {"wartosc": "189,50",
                            "dowod": "Kwota do zapłaty: 189,50 PLN"},
        "waluta": {"wartosc": "PLN", "dowod": "189,50 PLN"},
        "termin_platnosci": {"wartosc": "2026-12-01",
                             "dowod": "Termin płatności: 2026-12-01"},
        "numer_konta_bankowego": {"wartosc": KONTO,
                                  "dowod": "Rachunek bankowy: " + KONTO},
        "kategoria_sugerowana": {"wartosc": "Gaz", "dowod": "dostawa gazu"},
    })
    return wynik


class TestIban(unittest.TestCase):
    def test_poprawny_nrb_i_iban(self):
        self.assertTrue(poprawny_iban(KONTO))
        self.assertTrue(poprawny_iban(KONTO[2:]))
        self.assertEqual(zweryfikuj_numer_konta("  PL61 1090 1014 0000 0712 1981 2874 "), KONTO)

    def test_bledna_suma_kontrolna_i_znaki(self):
        self.assertFalse(poprawny_iban("PL62109010140000071219812874"))
        self.assertFalse(poprawny_iban("KONTO123"))
        self.assertEqual(zweryfikuj_numer_konta(""), "")
        with self.assertRaises(ValueError):
            zweryfikuj_numer_konta("PL62109010140000071219812874")


class TestOcena(unittest.TestCase):
    def test_poprawne_dane_i_brakujące_pola(self):
        wynik = ocena_json(odpowiedz_demo(), DANE, KATEGORIE)
        for p in ("dostawca", "numer_faktury", "kwota_do_zaplaty", "waluta",
                  "termin_platnosci", "numer_konta_bankowego", "kategoria_sugerowana"):
            self.assertTrue(wynik[p].poprawne, p)
        self.assertEqual(wynik["kwota_do_zaplaty"].wartosc, "189,50")
        self.assertEqual(wynik["numer_konta_bankowego"].wartosc, KONTO)
        self.assertFalse(wynik["data_wystawienia"].poprawne)

    def test_nieznana_kategoria_nie_jest_zastosowana(self):
        dane = odpowiedz_demo()
        dane["kategoria_sugerowana"]["wartosc"] = "dostawa gazu"
        wynik = ocena_json(dane, DANE, KATEGORIE)
        self.assertFalse(wynik["kategoria_sugerowana"].poprawne)

    def test_brak_dowodu_blokuje_wartosc(self):
        dane = odpowiedz_demo()
        dane["dostawca"]["dowod"] = "Nie ma takiego tekstu"
        self.assertFalse(ocena_json(dane, DANE, KATEGORIE)["dostawca"].poprawne)

    def test_niezweryfikowana_waluta_blokuje_kwote(self):
        dane = odpowiedz_demo()
        dane["waluta"]["wartosc"] = None
        dane["waluta"]["dowod"] = None
        wynik = ocena_json(dane, DANE, KATEGORIE)
        self.assertFalse(wynik["kwota_do_zaplaty"].poprawne)

    def test_bledna_data_i_numer_konta(self):
        dane = odpowiedz_demo()
        dane["termin_platnosci"]["wartosc"] = "2026-13-01"
        dane["numer_konta_bankowego"]["wartosc"] = "PL62109010140000071219812874"
        wynik = ocena_json(dane, DANE, KATEGORIE)
        self.assertFalse(wynik["termin_platnosci"].poprawne)
        self.assertFalse(wynik["numer_konta_bankowego"].poprawne)

    def test_odrzuca_niekompletny_json(self):
        dane = odpowiedz_demo()
        del dane["dostawca"]
        with self.assertRaises(ValueError):
            ocena_json(dane, DANE, KATEGORIE)

    def test_schemat_zawiera_wszystkie_pola(self):
        schemat = schemat_json(KATEGORIE)
        self.assertEqual(set(schemat["required"]), set(POLA))
        self.assertEqual(schemat["properties"]["kategoria_sugerowana"]
                         ["properties"]["wartosc"]["enum"], [*KATEGORIE, None])


class TestTransport(unittest.TestCase):
    def test_lokalne_api_bez_proxy_i_bez_zapisu(self):
        zwrot = {"message": {"content": json.dumps(odpowiedz_demo(), ensure_ascii=False)}}
        handler = MagicMock()
        handler.open.return_value.__enter__.return_value = io.BytesIO(
            json.dumps(zwrot, ensure_ascii=False).encode("utf-8")
        )
        with patch("uslugi.analiza_llm.build_opener", return_value=handler) as opener:
            analiza = analizuj_lokalnie(DANE, KATEGORIE)
        self.assertIsInstance(analiza, AnalizaModelu)
        self.assertEqual(analiza.model, "gemma3:4b")
        self.assertTrue(analiza.oceny["dostawca"].poprawne)
        request = handler.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "gemma3:4b")
        self.assertFalse(body["stream"])
        self.assertIn("format", body)
        self.assertIn("dostawa gazu", body["messages"][1]["content"])
        self.assertEqual(len(opener.call_args.args), 1)

    def test_za_dlugi_tekst_i_pusty(self):
        with self.assertRaises(ValueError):
            analizuj_lokalnie("x" * 30001, KATEGORIE)
        with self.assertRaises(ValueError):
            analizuj_lokalnie(" \n", KATEGORIE)


class TestMigracjaBank(unittest.TestCase):
    def test_migracja_ze_starej_bazy_zachowuje_dane(self):
        with tempfile.TemporaryDirectory() as tmp:
            katalog = Path(tmp)
            db = polacz(katalog / "swistak.sqlite3")
            try:
                poprzednie = katalog / "stare_migracje"
                poprzednie.mkdir()
                oryginal = Path(__file__).parents[1] / "baza" / "schemat" / "001_start.sql"
                (poprzednie / oryginal.name).write_bytes(oryginal.read_bytes())
                zastosuj_migracje(db, poprzednie)
                db.execute(
                    "INSERT INTO dokumenty (nazwa_zrodlowa, sha256, sciezka_wzgledna, rozmiar_bajtow) "
                    "VALUES ('syntetyczny.pdf', ?, 'dokumenty/ab/rachunek.pdf', 20)",
                    ("a" * 64,)
                )
                db.execute(
                    "INSERT INTO rachunki (dokument_id, dostawca, kwota_grosze) "
                    "VALUES (1, 'Test przed migracją', 999)"
                )
            finally:
                db.close()
            rejestr = RejestrRachunkow(katalog)
            try:
                wiersz = rejestr.rachunek(1)
                self.assertEqual(wiersz["kwota_grosze"], 999)
                self.assertEqual(wiersz["numer_konta"], "")
                self.assertEqual(len(rejestr.db.execute("SELECT * FROM migracje").fetchall()), 5)
                kopie = list((katalog / "kopie_migracji").glob("*.sqlite3"))
                self.assertEqual(len(kopie), 1)
                self.assertTrue(kopie[0].stat().st_size > 0)
            finally:
                rejestr.zamknij()

    def test_prawidlowy_konto_zapis_i_odczyt(self):
        with tempfile.TemporaryDirectory() as tmp:
            rejestr = RejestrRachunkow(Path(tmp) / "dane")
            try:
                pdf = Path(tmp) / "demo.pdf"
                pdf.write_bytes(b"%PDF-1.4\nsyntetyczny test\n%%EOF\n")
                dokument, _ = rejestr.importuj_pdf(pdf)
                kategoria = int(rejestr.kategorie()[0]["id"])
                dane = DaneRachunku(dokument, "Zakład", "FV-1", "189,50", kategoria,
                                   numer_konta=KONTO)
                rejestr.zapisz_rachunek(dane)
                self.assertEqual(rejestr.rachunek(dokument)["numer_konta"], KONTO)
            finally:
                rejestr.zamknij()


if __name__ == "__main__":
    unittest.main()
