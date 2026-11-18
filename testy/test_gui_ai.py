# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Test Qt offscreen: LLM może sugerować pola, lecz nie zapisuje rachunku."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QMessageBox

from testy.pomoc_qt import zamknij_widget
from gui.okno_glowne import OknoGlowne
from uslugi.analiza_llm import POLA, AnalizaModelu, ocena_json
from uslugi.odczyt_pdf import TekstStrony, WynikOdczytu
from uslugi.rachunki import RejestrRachunkow


class TestInterfejsAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sugestie_nie_zapisują_bez_akceptacji(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pdf_path = root / "syntetyczna-faktura.pdf"
            writer = QPdfWriter(str(pdf_path))
            painter = QPainter(writer)
            self.assertTrue(painter.isActive())
            painter.drawText(100, 200, "Syntetyczna faktura testowa")
            self.assertTrue(painter.end())
            rejestr = RejestrRachunkow(root / "dane")
            try:
                okno = OknoGlowne(rejestr)
                kreator = okno.kreator
                formularz = kreator.formularz
                odczyt = kreator.odczyt
                analiza = kreator.analiza
                okno.show()
                self.app.processEvents()
                okno.otworz_pdf(pdf_path)
                dokument_id = kreator.aktualny_dokument_id
                self.assertIsNotNone(dokument_id)
                self.assertIsNone(rejestr.rachunek(dokument_id))
                self.assertIs(kreator.pracuje, False)

                tresc_strony = (
                    "Sprzedawca: Zakład DEMO\n"
                    "Kwota do zapłaty: 189,50 PLN\n"
                    "Usługa: gaz\n"
                    "Termin płatności: 2026-12-01\n"
                )
                wynik_odczytu = WynikOdczytu((TekstStrony(0, tresc_strony, "ocr"),))
                tekst = wynik_odczytu.tekst_dla_llm
                with patch("gui.zakladka_odczytu.QThreadPool.globalInstance") as pool:
                    start = pool.return_value.start
                    odczyt.btn_odczytaj.click()
                    start.assert_called_once()
                    zadanie_odczytu = start.call_args.args[0]
                    self.assertTrue(odczyt.pracuje)
                    self.assertIs(kreator.pracuje, True)
                    self.assertFalse(analiza.btn_analizuj.isEnabled())
                    odczyt.btn_anuluj.click()
                    self.assertTrue(zadanie_odczytu.przerwij.is_set())
                    zadanie_odczytu.sygnaly.anulowano.emit()
                    self.assertIs(kreator.pracuje, False)
                    self.assertTrue(odczyt.btn_odczytaj.isEnabled())

                    odczyt.btn_odczytaj.click()
                    start.call_args.args[0].sygnaly.gotowe.emit(wynik_odczytu)
                    self.assertEqual(odczyt.tekst, tekst)
                    self.assertTrue(analiza.btn_analizuj.isEnabled())
                    odczyt.btn_analizuj_z_odczytu.click()
                    self.assertEqual(start.call_count, 3)
                    zadanie_analizy = start.call_args.args[0]
                    self.assertEqual(zadanie_analizy.tekst, tekst)
                    self.assertIs(kreator.pracuje, True)
                    self.assertFalse(odczyt.btn_odczytaj.isEnabled())
                    self.assertEqual(kreator.karty.currentIndex(), kreator.ETAP_ANALIZA)
                self.assertFalse(analiza.btn_przenies.isEnabled())
                self.assertIsNone(rejestr.rachunek(dokument_id))

                dane = {p: {"wartosc": None, "dowod": None} for p in POLA}
                dane["dostawca"] = {
                    "wartosc": "Zakład DEMO", "dowod": "Sprzedawca: Zakład DEMO"
                }
                dane["kwota_do_zaplaty"] = {
                    "wartosc": "189,50", "dowod": "Kwota do zapłaty: 189,50 PLN"
                }
                dane["waluta"] = {
                    "wartosc": "PLN", "dowod": "189,50 PLN"
                }
                dane["termin_platnosci"] = {
                    "wartosc": "2026-12-01", "dowod": "Termin płatności: 2026-12-01"
                }
                dane["kategoria_sugerowana"] = {
                    "wartosc": "Gaz", "dowod": "Usługa: gaz"
                }
                kategorie = [k["nazwa"] for k in rejestr.kategorie()]
                oceny = ocena_json(dane, tekst, kategorie)
                wynik = AnalizaModelu("gemma3:4b", oceny)
                zadanie_analizy.sygnaly.gotowe.emit(dokument_id, wynik)
                self.assertIs(kreator.pracuje, False)
                self.assertTrue(odczyt.btn_odczytaj.isEnabled())
                self.assertTrue(analiza.btn_przenies.isEnabled())
                self.assertIsNone(rejestr.rachunek(dokument_id))

                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
                    analiza.btn_przenies.click()
                self.assertFalse(formularz.ed_dostawca.text())
                self.assertIsNone(rejestr.rachunek(dokument_id))
                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                    analiza.btn_przenies.click()
                self.assertEqual(kreator.karty.currentIndex(), kreator.ETAP_EDYCJA)
                self.assertEqual(formularz.ed_dostawca.text(), "Zakład DEMO")
                self.assertEqual(formularz.ed_kwota.text(), "189,50")
                self.assertEqual(formularz.ed_termin.text(), "2026-12-01")
                self.assertEqual(formularz.wybor_kategoria.currentData(), next(int(row["id"]) for row in rejestr.kategorie() if row["nazwa"] == "Gaz"))
                self.assertIsNone(rejestr.rachunek(dokument_id))
                formularz.ed_wystawiono.setText("2026-11-02")
                kreator._zapisz_rachunek()  # odrębny, świadomy zapis
                self.assertEqual(rejestr.rachunek(dokument_id)["kwota_grosze"], 18950)
                zamknij_widget(okno)
            finally:
                rejestr.zamknij()


if __name__ == "__main__":
    unittest.main()
