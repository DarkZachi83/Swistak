# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Ochrona pełnego miesiąca oraz edycja wzorców — wyłącznie fikcyjne dane."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from gui.dialog_wzorca import DialogWzorca
from uslugi.analiza_llm import POLA, analizuj_lokalnie, ocena_json
from uslugi.dopasowanie_wzorca import zaproponuj_wzorzec
from uslugi.okres_rozliczeniowy import (
    popraw_okres_modelu, rozpoznaj_miesiac_rozliczenia,
)
from uslugi.wzorce import MagazynWzorcow


FIKCYJNY_OCR = (
    "Faktura DEMO\nSprzedawca: TEST Sieci\n"
    "Pozycja: abonament internetowy 11/2026 — 1 szt.\n"
    "Pozycja: utrzymanie linii - 11/2026\n"
    "Termin płatności: 15.12.2026\n"
    "Data wystawienia: 01.12.2026\n"
)


def surowa_odpowiedz(period_end: str = "2026-12-31") -> dict:
    fields = {p: {"wartosc": None, "dowod": None} for p in POLA}
    fields["okres_od"] = {
        "wartosc": "2026-11-01",
        "dowod": "abonament internetowy 11/2026",
    }
    fields["okres_do"] = {
        "wartosc": period_end,
        "dowod": "utrzymanie linii - 11/2026",
    }
    return fields


class TestOkresRozliczeniowy(unittest.TestCase):
    def test_listopad_zawsze_konczy_sie_30_dnia(self):
        period = rozpoznaj_miesiac_rozliczenia(FIKCYJNY_OCR)
        self.assertIsNotNone(period)
        self.assertEqual((period.od, period.do), ("2026-11-01", "2026-11-30"))
        self.assertIn("11/2026", period.dowod)

    def test_grudzien_i_luty_przestepny(self):
        cases = [
            ("Okres: 12/2026", "2026-12-01", "2026-12-31"),
            ("Abonament: 02/2028", "2028-02-01", "2028-02-29"),
            ("Usługa: 02/2027", "2027-02-01", "2027-02-28"),
        ]
        for text, start, finish in cases:
            with self.subTest(text=text):
                result = rozpoznaj_miesiac_rozliczenia(text)
                self.assertEqual((result.od, result.do), (start, finish))

    def test_dwuznaczne_okresy_nie_są_zgadywane(self):
        self.assertIsNone(rozpoznaj_miesiac_rozliczenia(
            "Usługa: 11/2026\nAbonament: 12/2026\n"
        ))
        self.assertIsNone(rozpoznaj_miesiac_rozliczenia(
            "Faktura nr 901/11/2026\nTermin płatności: 15.12.2026\n"
        ))
        self.assertIsNone(rozpoznaj_miesiac_rozliczenia(
            "Data wystawienia: 01.11.2026\nTermin płatności: 15.11.2026\n"
        ))

    def test_walidator_odrzuca_dwa_miesiace_mimo_poprawnych_dat(self):
        result = ocena_json(surowa_odpowiedz(), FIKCYJNY_OCR, ["Internet"])
        self.assertEqual(result["okres_od"].wartosc, "2026-11-01")
        self.assertTrue(result["okres_od"].poprawne)
        self.assertFalse(result["okres_do"].poprawne)
        self.assertIn("miesiącem rozliczeniowym", result["okres_do"].komunikat)

    def test_regula_koryguje_tylko_surowa_odpowiedz_gemmy(self):
        original = surowa_odpowiedz()
        adjusted, changed = popraw_okres_modelu(original, FIKCYJNY_OCR)
        self.assertEqual(changed, {"okres_do"})
        self.assertEqual(adjusted["okres_do"]["wartosc"], "2026-11-30")
        self.assertEqual(original["okres_do"]["wartosc"], "2026-12-31")
        validated = ocena_json(adjusted, FIKCYJNY_OCR, ["Internet"])
        self.assertTrue(validated["okres_do"].poprawne)

    def test_end_to_end_gemma_zla_data_nie_przechodzi_bez_poprawki(self):
        fake_answer = {"message": {"content": json.dumps(surowa_odpowiedz())}}
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.BytesIO(
            json.dumps(fake_answer).encode("utf-8")
        )
        with patch("uslugi.analiza_llm.build_opener", return_value=opener):
            result = analizuj_lokalnie(FIKCYJNY_OCR, ["Internet"], "demo-llm:1")
        self.assertEqual(result.oceny["okres_od"].wartosc, "2026-11-01")
        self.assertEqual(result.oceny["okres_do"].wartosc, "2026-11-30")
        self.assertTrue(result.oceny["okres_do"].poprawne)
        self.assertIn("wyliczony", result.oceny["okres_do"].komunikat)


class TestFormularzWzorca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wzorzec(self):
        return zaproponuj_wzorzec(
            "Sprzedawca:\nSieci DEMO\nNIP: 123-456-32-18\n"
            "Data wystawienia: 11.11.2026\n"
            "Termin płatności: 21.11.2026\n"
            "Okres rozliczeniowy: 11/2026\n",
            "Sieci DEMO", "Internet",
            {"termin_platnosci": "Wyszukaj datę w nagłówku"},
        )

    def test_formularz_edycja_podglad_i_zapis_przez_zgode(self):
        with tempfile.TemporaryDirectory() as td:
            store = MagazynWzorcow(Path(td))
            dialog = DialogWzorca(None, self._wzorzec())
            self.assertEqual(dialog.karty.count(), 3)
            self.assertTrue(dialog.podglad.isReadOnly())
            self.assertEqual(len(dialog.pola), len(POLA))
            self.assertTrue(dialog.pola["termin_platnosci"]["group"].isChecked())
            dialog.nazwa.setText("Internet DEMO — poprawiony szablon")
            dialog.pola["termin_platnosci"]["note"].setPlainText(
                "Porównaj termin z prawym nagłówkiem"
            )
            dialog.pola["okres_do"]["source_format"].setCurrentText("MM/RRRR")
            dialog.pola["okres_do"]["target_format"].setCurrentText("RRRR-MM-DD")
            dialog.karty.setCurrentIndex(2)
            self.app.processEvents()
            preview = json.loads(dialog.podglad.toPlainText())
            self.assertEqual(preview["name"], "Internet DEMO — poprawiony szablon")
            self.assertIn("prawym nagłówkiem", preview["fields"]["termin_platnosci"]["note"])
            self.assertEqual(store.lista(), [])  # dialog nie zapisuje plików
            dialog._zatwierdz()
            self.assertIsNotNone(dialog.zatwierdzone)
            self.assertEqual(store.lista(), [])  # samo zatwierdzenie dialogu też nie
            saved = store.utworz(dialog.zatwierdzone)
            self.assertEqual(saved["name"], "Internet DEMO — poprawiony szablon")
            self.assertEqual(
                store.pobierz(saved["template_id"])["fields"]["okres_do"]["target_format"],
                "RRRR-MM-DD",
            )

    def test_wylaczenie_reguly_i_anulowanie(self):
        dialog = DialogWzorca(None, self._wzorzec(), aktualizacja=True)
        dialog.pola["okres_do"]["group"].setChecked(False)
        data = dialog.zbuduj_dane()
        self.assertNotIn("okres_do", data["fields"])
        self.assertIn("termin_platnosci", data["fields"])
        dialog.reject()
        self.assertIsNone(dialog.zatwierdzone)

    def test_ochrona_poufnych_wartosci_w_notatkach(self):
        dialog = DialogWzorca(None, self._wzorzec())
        dialog.wskazowki.setPlainText(
            "Nie wpisuj numeru 12 3456 7890 1234 5678 9012 3456"
        )
        with self.assertRaises(ValueError):
            dialog.zbuduj_dane()
        dialog.reject()


if __name__ == "__main__":
    unittest.main()
