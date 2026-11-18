# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Przebudowa panelu Analiza AI: DANE / AGENT; tylko fikcyjne dokumenty."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import (
    QApplication, QInputDialog, QMessageBox,
)

import ustawienia
from gui.okno_glowne import OknoGlowne
from uslugi.analiza_llm import POLA
from uslugi.rachunki import RejestrRachunkow


class TestZakladkiAnalizy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def stworz_fikcyjny_pdf(sciezka: Path) -> None:
        writer = QPdfWriter(str(sciezka))
        painter = QPainter(writer)
        try:
            if not painter.isActive():
                raise RuntimeError("Błąd syntetycznego PDF")
            painter.drawText(100, 130, "FIKCYJNA FAKTURA " + sciezka.stem)
        finally:
            if painter.isActive():
                painter.end()

    def test_dwie_zakladki_i_stala_sekcja_danych(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "prefs.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    kreator = win.kreator
                    try:
                        self.assertEqual(kreator.zakladki_ai.count(), 2)
                        self.assertEqual(kreator.zakladki_ai.tabText(0), "DANE")
                        self.assertEqual(kreator.zakladki_ai.tabText(1), "AGENT")
                        self.assertEqual(kreator.zakladki_ai.currentIndex(), 0)
                        self.assertEqual(kreator.tabela_ai.columnCount(), 5)
                        self.assertEqual(kreator.tabela_ai.horizontalHeaderItem(4).text(),
                                         "Komentarz")
                        self.assertTrue(kreator.karta_ai_dane.isAncestorOf(kreator.tabela_ai))
                        self.assertTrue(kreator.karta_ai_dane.isAncestorOf(kreator.btn_analizuj))
                        self.assertTrue(kreator.karta_ai_dane.isAncestorOf(kreator.btn_przenies))
                        self.assertTrue(kreator.karta_ai_dane.isAncestorOf(kreator.btn_info_ai))
                        self.assertTrue(kreator.karta_ai_agent.isAncestorOf(kreator.ed_model))
                        self.assertTrue(kreator.karta_ai_agent.isAncestorOf(
                            kreator.btn_wybierz_wzorzec
                        ))
                        self.assertTrue(kreator.karta_ai_agent.isAncestorOf(
                            kreator.notatki_wzorca
                        ))
                        with patch.object(QMessageBox, "information") as info:
                            kreator.btn_info_ai.click()
                            info.assert_called_once()
                            self.assertIn("INFO", info.call_args.args[1])
                            self.assertIn("Odczyt PDF", info.call_args.args[2])
                    finally:
                        win.close()
            finally:
                db.zamknij()

    def test_komentarze_jezyk_i_przelaczanie_bez_utracenia_danych(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_a = root / "faktura-a.pdf"
            pdf_b = root / "faktura-b.pdf"
            self.stworz_fikcyjny_pdf(pdf_a)
            self.stworz_fikcyjny_pdf(pdf_b)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "prefs.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    kreator = win.kreator
                    try:
                        win.otworz_pdf(pdf_a)
                        field = POLA[0]
                        note = "Szukaj nazwy bezpośrednio nad tabelą"
                        with patch.object(QInputDialog, "getMultiLineText",
                                          return_value=(note, True)):
                            kreator.tabela_ai.itemDoubleClicked.emit(
                                kreator.tabela_ai.item(0, 4)
                            )
                        self.assertEqual(kreator._komentarze_wzorca[field], note)
                        self.assertEqual(kreator.tabela_ai.item(0, 4).text(), note)

                        kreator.zakladki_ai.setCurrentIndex(1)
                        kreator.ed_model.setText("synthetic:4b")
                        kreator.notatki_wzorca.setPlainText("Zasada bez danych nabywcy")
                        win.change_language("en")
                        self.assertEqual(kreator.zakladki_ai.tabText(0), "DATA")
                        self.assertEqual(kreator.zakladki_ai.tabText(1), "AGENT")
                        self.assertEqual(kreator.zakladki_ai.currentIndex(), 1)
                        self.assertEqual(kreator.ed_model.text(), "synthetic:4b")
                        self.assertEqual(
                            kreator.notatki_wzorca.toPlainText(),
                            "Zasada bez danych nabywcy",
                        )
                        self.assertEqual(kreator.tabela_ai.horizontalHeaderItem(4).text(),
                                         "Comment")
                        self.assertEqual(kreator.tabela_ai.item(0, 4).text(), note)
                        kreator.zakladki_ai.setCurrentIndex(0)
                        self.assertEqual(kreator._komentarze_wzorca[field], note)

                        # Nowa faktura nie może odziedziczyć uwag poprzedniej.
                        win.otworz_pdf(pdf_b)
                        self.assertEqual(kreator._komentarze_wzorca, {})
                        self.assertEqual(kreator.tabela_ai.item(0, 4).text(), "—")
                        self.assertEqual(kreator.notatki_wzorca.toPlainText(), "")
                    finally:
                        win.close()
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
