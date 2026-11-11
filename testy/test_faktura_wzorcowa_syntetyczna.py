# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Test wzorcowego PRZEPŁYWU, wyłącznie z fikcyjnymi danymi.

NIGDY nie dołączać tu rzeczywistych faktur ani danych prywatnych.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

import ustawienia
from gui.okno_glowne import OknoGlowne
from uslugi.analiza_llm import POLA, AnalizaModelu, ocena_json, normalizuj_date
from uslugi.rachunki import RejestrRachunkow


DEMO_TEKST = (
    "Sprzedawca:\nFirma Testowa Sieć DEMO\n"
    "Data wystawienia: 03.11.2026\n"
    "Termin płatności: 21.11.2026\n"
    "Okres: 11/2026\n"
    "Usługa internetu - przykładowy abonament\n"
    "Kwota do zapłaty: 77,50 PLN\n"
)


def dane_demo() -> dict:
    wynik = {p: {"wartosc": None, "dowod": None} for p in POLA}
    wynik.update({
        "dostawca": {
            "wartosc": "Firma Testowa Sieć DEMO",
            "dowod": "Sprzedawca: Firma Testowa Sieć DEMO",
        },
        "numer_faktury": {
            "wartosc": "FIK/123/2026",
            "dowod": None,  # brak dowodu — nie wolno przenieść automatycznie
        },
        "kwota_do_zaplaty": {
            "wartosc": "77,50", "dowod": "Kwota do zapłaty: 77,50 PLN",
        },
        "waluta": {"wartosc": "PLN", "dowod": "77,50 PLN"},
        "data_wystawienia": {
            "wartosc": "03.11.2026", "dowod": "Data wystawienia: 03.11.2026",
        },
        "termin_platnosci": {
            "wartosc": "21.11.2026", "dowod": "Termin płatności: 21.11.2026",
        },
        "okres_od": {"wartosc": "11/2026", "dowod": "Okres: 11/2026"},
        "okres_do": {"wartosc": "11/2026", "dowod": "Okres: 11/2026"},
        "kategoria_sugerowana": {
            "wartosc": "Internet", "dowod": "Usługa internetu - przykładowy abonament",
        },
    })
    return wynik


class TestWalidacjaFakturySyntetycznej(unittest.TestCase):
    def test_polskie_daty_i_miesieczny_okres(self):
        self.assertEqual(normalizuj_date("03.11.2026", "data_wystawienia"),
                         "2026-11-03")
        self.assertEqual(normalizuj_date("2026-11-21", "termin_platnosci"),
                         "2026-11-21")
        self.assertEqual(normalizuj_date("11/2026", "okres_od"),
                         "2026-11-01")
        self.assertEqual(normalizuj_date("11/2026", "okres_do"),
                         "2026-11-30")
        self.assertEqual(normalizuj_date("02/2028", "okres_do"),
                         "2028-02-29")
        for bad, field in (
            ("32.11.2026", "data_wystawienia"),
            ("2026-13-01", "termin_platnosci"),
            ("11/2026", "data_wystawienia"),
            ("13/2026", "okres_od"),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    normalizuj_date(bad, field)

    def test_dowod_ze_zlamaniem_linii_kategoria_i_potwierdzenie(self):
        oceny = ocena_json(dane_demo(), DEMO_TEKST, ["Inne", "Telefon"])
        self.assertTrue(oceny["dostawca"].poprawne)
        self.assertEqual(oceny["data_wystawienia"].wartosc, "2026-11-03")
        self.assertEqual(oceny["termin_platnosci"].wartosc, "2026-11-21")
        self.assertEqual(oceny["okres_od"].wartosc, "2026-11-01")
        self.assertEqual(oceny["okres_do"].wartosc, "2026-11-30")
        self.assertFalse(oceny["kategoria_sugerowana"].poprawne)
        self.assertFalse(oceny["numer_faktury"].poprawne)

        po_dodaniu = ocena_json(dane_demo(), DEMO_TEKST, ["Internet", "Inne"])
        self.assertTrue(po_dodaniu["kategoria_sugerowana"].poprawne)
        poprawione = dane_demo()
        poprawione["data_wystawienia"]["wartosc"] = "04.11.2026"
        bez_potwierdzenia = ocena_json(poprawione, DEMO_TEKST, ["Internet"])
        self.assertFalse(bez_potwierdzenia["data_wystawienia"].poprawne)
        po_potwierdzeniu = ocena_json(
            poprawione, DEMO_TEKST, ["Internet"],
            potwierdzone_recznie={"data_wystawienia"},
        )
        self.assertTrue(po_potwierdzeniu["data_wystawienia"].poprawne)
        self.assertEqual(po_potwierdzeniu["data_wystawienia"].wartosc,
                         "2026-11-04")

        # Ręczne potwierdzenie NIE omija walidacji numeru konta.
        zle_konto = dane_demo()
        zle_konto["numer_konta_bankowego"] = {
            "wartosc": "PL00000000000000000000000000", "dowod": None,
        }
        walidacja = ocena_json(
            zle_konto, DEMO_TEKST, ["Internet"],
            potwierdzone_recznie={"numer_konta_bankowego"},
        )
        self.assertFalse(walidacja["numer_konta_bankowego"].poprawne)


class TestKorektaAIWInterfejsie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _pdf(path: Path):
        writer = QPdfWriter(str(path))
        painter = QPainter(writer)
        if not painter.isActive():
            raise RuntimeError("Nie można utworzyć PDF demo")
        painter.drawText(100, 110, "Syntetyczna faktura internetowa DEMO")
        painter.end()

    def test_edycja_dat_i_dodanie_kategorii_bez_automatycznego_zapisu(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            pdf = folder / "tylko-syntetyczna-faktura.pdf"
            self._pdf(pdf)
            db = RejestrRachunkow(folder / "testowe-dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=folder / "ustawienia.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    win.show()
                    self.app.processEvents()
                    win.otworz_pdf(pdf)
                    document_id = win.aktualny_dokument_id
                    self.assertIsNotNone(document_id)
                    win.pole_odczytu.setPlainText(DEMO_TEKST)
                    win._aktualizuj_odczyt()

                    wynik = AnalizaModelu(
                        "mock-llm",
                        ocena_json(dane_demo(), DEMO_TEKST,
                                   [r["nazwa"] for r in db.kategorie()]),
                    )
                    win._analiza_gotowa(document_id, wynik)
                    row_date = POLA.index("data_wystawienia")
                    row_category = POLA.index("kategoria_sugerowana")
                    self.assertTrue(win.tabela_ai.item(row_date, 1).flags()
                                    & Qt.ItemFlag.ItemIsEditable)
                    self.assertFalse(win.tabela_ai.item(row_date, 2).flags()
                                     & Qt.ItemFlag.ItemIsEditable)
                    self.assertEqual(win.tabela_ai.item(row_date, 1).text(),
                                     "2026-11-03")
                    self.assertFalse(win._analiza.oceny["kategoria_sugerowana"].poprawne)
                    self.assertIsNone(db.rachunek(document_id))

                    # Po zmianie AI nie może uznać nowej daty bez dowodu.
                    win.tabela_ai.item(row_date, 1).setText("04.11.2026")
                    self.assertFalse(win._analiza.oceny["data_wystawienia"].poprawne)
                    win.tabela_ai.setCurrentCell(row_date, 1)
                    with patch.object(QMessageBox, "question",
                                      return_value=QMessageBox.StandardButton.Yes):
                        win._potwierdz_pole_ai()
                    self.assertTrue(win._analiza.oceny["data_wystawienia"].poprawne)
                    self.assertEqual(win.tabela_ai.item(row_date, 1).text(), "2026-11-04")

                    # Nowa kategoria zdefiniowana przez użytkownika na ekranie AI.
                    win.karty.setCurrentIndex(win.ETAP_ANALIZA)
                    with patch.object(QInputDialog, "getText",
                                      return_value=("Internet", True)):
                        win._dodaj_kategorie()
                    self.assertEqual(win.tabela_ai.item(row_category, 1).text(),
                                     "Internet")
                    self.assertTrue(win._analiza.oceny["kategoria_sugerowana"].poprawne)
                    self.assertIn("Internet",
                                  [x["nazwa"] for x in db.kategorie()])
                    self.assertIsNone(db.rachunek(document_id))

                    # Przeniesienie do edycji ≠ zapis faktury.
                    with patch.object(QMessageBox, "question",
                                      return_value=QMessageBox.StandardButton.Yes):
                        win._przenies_sugestie()
                    self.assertEqual(win.karty.currentIndex(), win.ETAP_EDYCJA)
                    self.assertEqual(win.ed_wystawiono.text(), "2026-11-04")
                    self.assertEqual(win.ed_dostawca.text(),
                                     "Firma Testowa Sieć DEMO")
                    self.assertEqual(win.ed_kwota.text(), "77,50")
                    self.assertEqual(win.wybor_kategoria.currentText(), "Internet")
                    self.assertIsNone(db.rachunek(document_id))
                    win.btn_przejdz_faktura.click()
                    self.assertIsNone(db.rachunek(document_id))
                    win.zapisz_przycisk.click()
                    self.assertEqual(db.rachunek(document_id)["kwota_grosze"], 7750)
                    win.close()
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
