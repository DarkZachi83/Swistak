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
from testy.pomoc_qt import zamknij_widget
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
                    analiza = kreator.analiza
                    try:
                        self.assertEqual(analiza.zakladki_ai.count(), 2)
                        self.assertEqual(analiza.zakladki_ai.tabText(0), "DANE")
                        self.assertEqual(analiza.zakladki_ai.tabText(1), "AGENT")
                        self.assertEqual(analiza.zakladki_ai.currentIndex(), 0)
                        self.assertEqual(analiza.tabela_ai.columnCount(), 5)
                        self.assertEqual(analiza.tabela_ai.horizontalHeaderItem(4).text(),
                                         "Komentarz")
                        self.assertTrue(analiza.karta_ai_dane.isAncestorOf(analiza.tabela_ai))
                        self.assertTrue(analiza.karta_ai_dane.isAncestorOf(analiza.btn_analizuj))
                        self.assertTrue(analiza.karta_ai_dane.isAncestorOf(analiza.btn_przenies))
                        self.assertTrue(analiza.karta_ai_dane.isAncestorOf(analiza.btn_info_ai))
                        self.assertTrue(analiza.karta_ai_agent.isAncestorOf(analiza.ed_model))
                        self.assertTrue(analiza.karta_ai_agent.isAncestorOf(
                            analiza.btn_wybierz_wzorzec
                        ))
                        self.assertTrue(analiza.karta_ai_agent.isAncestorOf(
                            analiza.notatki_wzorca
                        ))
                        with patch.object(QMessageBox, "information") as info:
                            analiza.btn_info_ai.click()
                            info.assert_called_once()
                            self.assertIn("INFO", info.call_args.args[1])
                            self.assertIn("Odczyt PDF", info.call_args.args[2])
                    finally:
                        zamknij_widget(win)
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
                    analiza = kreator.analiza
                    try:
                        win.otworz_pdf(pdf_a)
                        field = POLA[0]
                        note = "Szukaj nazwy bezpośrednio nad tabelą"
                        with patch.object(QInputDialog, "getMultiLineText",
                                          return_value=(note, True)):
                            analiza.tabela_ai.itemDoubleClicked.emit(
                                analiza.tabela_ai.item(0, 4)
                            )
                        self.assertEqual(analiza._komentarze_wzorca[field], note)
                        self.assertEqual(analiza.tabela_ai.item(0, 4).text(), note)

                        analiza.zakladki_ai.setCurrentIndex(1)
                        analiza.ed_model.setText("synthetic:4b")
                        analiza.notatki_wzorca.setPlainText("Zasada bez danych nabywcy")
                        win.change_language("en")
                        self.assertEqual(analiza.zakladki_ai.tabText(0), "DATA")
                        self.assertEqual(analiza.zakladki_ai.tabText(1), "AGENT")
                        self.assertEqual(analiza.zakladki_ai.currentIndex(), 1)
                        self.assertEqual(analiza.ed_model.text(), "synthetic:4b")
                        self.assertEqual(
                            analiza.notatki_wzorca.toPlainText(),
                            "Zasada bez danych nabywcy",
                        )
                        self.assertEqual(analiza.tabela_ai.horizontalHeaderItem(4).text(),
                                         "Comment")
                        self.assertEqual(analiza.tabela_ai.item(0, 4).text(), note)
                        analiza.zakladki_ai.setCurrentIndex(0)
                        self.assertEqual(analiza._komentarze_wzorca[field], note)

                        # Nowa faktura nie może odziedziczyć uwag poprzedniej.
                        win.otworz_pdf(pdf_b)
                        self.assertEqual(analiza._komentarze_wzorca, {})
                        self.assertEqual(analiza.tabela_ai.item(0, 4).text(), "—")
                        self.assertEqual(analiza.notatki_wzorca.toPlainText(), "")
                    finally:
                        zamknij_widget(win)
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
