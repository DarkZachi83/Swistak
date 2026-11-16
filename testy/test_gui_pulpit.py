# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""GUI-1: odczyt syntetycznej bazy, nawigacja i zachowanie otwartej faktury."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import ustawienia
from ai_core.hybrid import MonitorReport
from gui.dialog_plan_historia import DialogPlanHistoria
from gui.okno_glowne import OknoGlowne
from i18n import current_language, set_language
from uslugi.finanse import Finanse
from uslugi.historia import HistoriaRozliczen
from uslugi.plan_rachunkow import PlanRachunkow
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class TestPulpit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.addCleanup(set_language, current_language())
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temp)
        self.rejestr = RejestrRachunkow(self.root / "dane")
        self.addCleanup(self.rejestr.zamknij)
        self.finanse = Finanse(self.rejestr.db)
        self.plan = PlanRachunkow(self.rejestr.db)
        self.kategoria = self.rejestr.kategorie()[0]["id"]
        self.enterContext(patch.object(ustawienia, "path_settings",
                                       return_value=self.root / "config.json"))
        self.enterContext(patch("gui.pulpit.today_warsaw", return_value="2026-11-16"))
        ustawienia.save({"language": "pl", "ollama_model": "demo:1"})

    def okno(self):
        window = OknoGlowne(self.rejestr)
        self.addCleanup(window.close)
        window.show()
        window._agent_timer.stop()
        self.app.processEvents()
        return window

    def faktura(self, numer, kwota, *, termin="", okres_do="2026-11-30",
                wystawiono="2026-11-03", status="do_zaplaty"):
        pdf = self.root / f"{numer}.pdf"
        pdf.write_text(f"%PDF-1.4\n% Syntetyczny {numer}\n%%EOF", encoding="ascii")
        dokument_id, _ = self.rejestr.importuj_pdf(pdf)
        return self.rejestr.zapisz_rachunek(DaneRachunku(
            dokument_id=dokument_id, dostawca="DEMO", numer=numer, kwota=kwota,
            kategoria_id=self.kategoria, termin_platnosci=termin, okres_do=okres_do,
            data_wystawienia=wystawiono, status=status,
        ))

    def test_pusta_baza_startuje_na_pulpicie_bez_ollamy(self):
        with patch("gui.okno_glowne.ZadanieMonitora") as worker:
            window = self.okno()
            self.assertIs(window.moduly.currentWidget(), window.pulpit)
            self.assertTrue(window.nawigacja_glowna["dashboard"].isChecked())
            self.assertFalse(window.nawigacja_glowna["statistics"].isEnabled())
            self.assertEqual(window.pulpit.miesiac.currentText(), "2026-11")
            for klucz, pole in window.pulpit.wartosci.items():
                self.assertEqual(pole.text(), "0,00 zł" if klucz in window.pulpit.opisy else "0")
            self.assertTrue(window.pulpit.brak_oczekiwan.isVisible())
            worker.assert_not_called()

    def test_terminy_i_miesiace_liczone_z_prawdziwych_groszy(self):
        self.faktura("po-terminie", "1,01", termin="2026-11-15", okres_do="2026-10-31")
        self.faktura("dzis", "2,02", termin="2026-11-16")
        self.faktura("granica", "3,03", termin="2026-11-23")
        self.faktura("za-pozno", "4,04", termin="2026-11-24")
        self.faktura("bez-terminu", "5,05", okres_do="", wystawiono="")
        self.faktura("oplacona-bez-daty", "6,06", termin="2026-11-14", status="oplacony")
        stara = self.faktura("stara", "7,07", okres_do="2026-10-31")
        nowa = self.faktura("nowa", "8,08", okres_do="")
        wycofana = self.faktura("wycofana", "99,99", termin="2026-11-15")
        self.finanse.wycofaj(wycofana, powod="Test")
        self.finanse.ustaw_oplacona(stara, "2026-11-12")
        self.finanse.ustaw_oplacona(nowa, "2026-12-01")

        self.assertEqual(self.finanse.podsumowanie_terminow(date(2026, 11, 16)), {
            "unpaid_count": 5, "unpaid_grosze": 1515,
            "overdue_count": 1, "overdue_grosze": 101,
            "due_soon_count": 2, "due_soon_grosze": 505,
        })
        window = self.okno()
        pola = window.pulpit.wartosci
        self.assertEqual(pola["unpaid"].text(), "15,15 zł")
        self.assertEqual(pola["overdue"].text(), "1,01 zł")
        self.assertEqual(pola["due_soon"].text(), "5,05 zł")
        self.assertEqual(pola["billed"].text(), "23,23 zł")
        self.assertEqual(pola["paid_service"].text(), "14,14 zł")
        self.assertEqual(pola["payments_in_month"].text(), "7,07 zł")
        self.assertEqual(window.pulpit.opisy["paid_service"].text(), "Liczba faktur: 2")
        window.pulpit.miesiac.setCurrentText("2026-10")
        self.assertEqual(pola["billed"].text(), "8,08 zł")
        self.assertEqual(pola["payments_in_month"].text(), "0,00 zł")
        self.assertEqual(pola["unpaid"].text(), "15,15 zł")

        ident = self.faktura("odswiezenie", "0,10", termin="2026-11-16")
        with patch.object(window, "_agent_submit"):
            window._plan_financial_change(ident)
        self.assertEqual(pola["due_soon"].text(), "5,15 zł")
        self.assertEqual(window.pulpit.miesiac.currentText(), "2026-10")

    def test_sumy_miesiaca_obejmuja_wszystkie_faktury(self):
        db = self.rejestr.db
        db.executemany(
            "INSERT INTO dokumenty(nazwa_zrodlowa,sha256,sciezka_wzgledna,rozmiar_bajtow) "
            "VALUES ('test.pdf', ?, ?, 1)",
            ((f"{i:064x}", f"test-{i}.pdf") for i in range(501)),
        )
        db.execute(
            "INSERT INTO rachunki(dokument_id,dostawca,data_wystawienia,kwota_grosze) "
            "SELECT id,'Syntetyczny','2026-11-02',1 FROM dokumenty"
        )
        historia = HistoriaRozliczen(db)
        self.assertEqual(len(historia.faktury("2026-11")), 500)
        self.assertEqual(historia.miesiac("2026-11")["billed_grosze"], 501)

    def test_oczekiwania_i_raport_agenta(self):
        ident = self.faktura("otrzymana", "1,00")
        for nazwa, przesuniecie in (
            ("Oczekiwanie", 0), ("Brak", -20), ("Niepewny", -20),
            ("Otrzymany", -20), ("Niewystawiony", -20),
        ):
            self.plan.utworz_profil(
                nazwa, cykl_od="2026-11", przesuniecie_dni=przesuniecie
            )
        self.plan.generuj_oczekiwania("2026-11")
        oczekiwania = {
            row["nazwa"]: row["id"]
            for row in HistoriaRozliczen(self.rejestr.db).oczekiwania("2026-11")
        }
        self.plan.oznacz_wyjatek(oczekiwania["Niepewny"], typ="niepewne", powod="Test")
        self.plan.oznacz_wyjatek(oczekiwania["Niewystawiony"], typ="nie_wystawiono", powod="Test")
        self.plan.powiaz(oczekiwania["Otrzymany"], ident)
        zmiany = self.rejestr.db.total_changes

        window = self.okno()
        for klucz in ("waiting", "missing", "uncertain"):
            self.assertEqual(window.pulpit.wartosci[klucz].text(), "1")
        self.assertFalse(window.pulpit.brak_oczekiwan.isVisible())
        self.assertEqual(self.rejestr.db.total_changes, zmiany)
        window._agent_completed(MonitorReport(
            mode="startup", invoice_id=None, reference_date="2026-11-16",
            data_revision="syntetyczna", summary={}, model_status="local_only",
        ))
        self.assertIn("bez LLM", window.pulpit.stan_agenta.text())
        self.assertIn("Analiza przy starcie · 2026-11-16", window.pulpit.raport_agenta.text())

    def test_nawigacja_i_tlumaczenie_zachowuja_pdf_i_edycje(self):
        window = self.okno()
        nav = window.nawigacja_glowna
        pdf = self.root / "roboczy.pdf"
        writer = QPdfWriter(str(pdf))
        painter = QPainter(writer)
        painter.drawText(100, 100, "Syntetyczny rachunek")
        self.assertTrue(writer.newPage())
        painter.drawText(100, 100, "Druga strona")
        self.assertTrue(painter.end())

        with patch("gui.okno_glowne.QFileDialog.getOpenFileName", return_value=(str(pdf), "")):
            window.akcja_import.trigger()
        ident = window.aktualny_dokument_id
        self.assertIsNotNone(ident)
        self.assertIs(window.moduly.currentWidget(), window.kreator)
        QTest.mouseClick(nav["new_invoice"], Qt.MouseButton.LeftButton)
        window.karty.setCurrentIndex(window.ETAP_EDYCJA)
        window.podglad.pokaz_strone(1)
        window.ed_kwota.setText("123,45")
        window.pole_odczytu.setPlainText("Tekst z OCR")

        QTest.mouseClick(nav["dashboard"], Qt.MouseButton.LeftButton)
        window.change_language("en")
        self.assertEqual(window.pulpit.naglowek.text(), "Dashboard")
        self.assertEqual(nav["new_invoice"].text(), "New invoice")
        self.assertEqual(window.pulpit.wartosci["unpaid"].text(), "0,00 PLN")
        QTest.mouseClick(nav["invoices"], Qt.MouseButton.LeftButton)
        self.assertIs(window.karty.currentWidget(), window.tabela_faktur)
        self.assertTrue(nav["invoices"].isChecked())
        QTest.mouseClick(nav["new_invoice"], Qt.MouseButton.LeftButton)
        self.assertEqual(window.karty.currentIndex(), window.ETAP_EDYCJA)
        self.assertEqual(window.aktualny_dokument_id, ident)
        self.assertEqual(window.podglad.strona, 1)
        self.assertEqual(window.podglad.liczba_stron, 2)
        self.assertEqual(window.ed_kwota.text(), "123,45")
        self.assertEqual(window.pole_odczytu.toPlainText(), "Tekst z OCR")
        self.assertEqual(window.nawigacja.count(), 6)

    def test_plan_i_historia_otwieraja_wlasciwe_karty(self):
        self.faktura("historyczna", "1,00", okres_do="2026-10-31")
        window = self.okno()
        okna = []

        def zapisz_widok(dialog):
            okna.append((dialog.tabs.currentIndex(), dialog.month.currentText()))
            return 0

        with patch.object(DialogPlanHistoria, "exec", zapisz_widok):
            window.nawigacja_glowna["plan"].click()
            window.nawigacja_glowna["history"].click()
            window.pulpit.miesiac.setCurrentText("2026-10")
            przycisk = next(w for w, k in window.pulpit.napisy if k == "plan.tab.history")
            przycisk.click()
        self.assertEqual(okna, [(0, "2026-11"), (1, "2026-11"), (1, "2026-10")])
        self.assertTrue(window.nawigacja_glowna["dashboard"].isChecked())
