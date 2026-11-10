# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Test Qt offscreen: LLM może sugerować pola, lecz nie zapisuje rachunku."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.okno_glowne import OknoGlowne
from uslugi.analiza_llm import POLA, AnalizaModelu, ocena_json
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
                okno.show()
                self.app.processEvents()
                okno.otworz_pdf(pdf_path)
                dokument_id = okno.aktualny_dokument_id
                self.assertIsNotNone(dokument_id)
                self.assertIsNone(rejestr.rachunek(dokument_id))

                tekst = (
                    "Sprzedawca: Zakład DEMO\n"
                    "Kwota do zapłaty: 189,50 PLN\n"
                    "Usługa: gaz\n"
                    "Termin płatności: 2026-12-01\n"
                )
                okno.pole_odczytu.setPlainText(tekst)
                okno._aktualizuj_odczyt()
                self.assertTrue(okno.btn_analizuj.isEnabled())
                with patch("gui.okno_glowne.QThreadPool.globalInstance") as pool:
                    okno._start_analizy()
                    pool.return_value.start.assert_called_once()
                self.assertFalse(okno.btn_przenies.isEnabled())
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
                okno._analiza_gotowa(dokument_id, wynik)
                self.assertTrue(okno.btn_przenies.isEnabled())
                self.assertIsNone(rejestr.rachunek(dokument_id))

                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
                    okno._przenies_sugestie()
                self.assertFalse(okno.ed_dostawca.text())
                self.assertIsNone(rejestr.rachunek(dokument_id))
                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                    okno._przenies_sugestie()
                self.assertEqual(okno.ed_dostawca.text(), "Zakład DEMO")
                self.assertEqual(okno.ed_kwota.text(), "189,50")
                self.assertEqual(okno.ed_termin.text(), "2026-12-01")
                self.assertEqual(okno.wybor_kategoria.currentData(), next(int(row["id"]) for row in rejestr.kategorie() if row["nazwa"] == "Gaz"))
                self.assertIsNone(rejestr.rachunek(dokument_id))
                okno._zapisz_rachunek()  # odrębny, świadomy zapis
                self.assertEqual(rejestr.rachunek(dokument_id)["kwota_grosze"], 18950)
                okno.close()
            finally:
                rejestr.zamknij()


if __name__ == "__main__":
    unittest.main()
