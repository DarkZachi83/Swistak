# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""GUI-2: zestawienia SQLite i interakcje widoku na danych syntetycznych."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

import ustawienia
from gui.okno_glowne import OknoGlowne
from i18n import current_language, set_language
from uslugi.finanse import Finanse
from uslugi.historia import HistoriaRozliczen
from uslugi.rachunki import DaneRachunku, RejestrRachunkow
from uslugi.statystyki import BEZ_KATEGORII, StatystykiRachunkow, ZakresDat


LISTOPAD = ZakresDat(date(2026, 11, 1), date(2026, 11, 30))


class BazaStatystyk(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.rejestr = RejestrRachunkow(self.root / "dane")
        self.addCleanup(self.rejestr.zamknij)
        self.db = self.rejestr.db
        self.stat = StatystykiRachunkow(self.db)
        self.finanse = Finanse(self.db)
        self.kategorie = {w["nazwa"]: w["id"] for w in self.rejestr.kategorie()}
        self.gaz = self.kategorie["Gaz"]
        self.prad = self.kategorie["Energia elektryczna"]

    def faktura(self, numer, kwota, *, usluga="", wystawiono="2026-11-10",
                dostawca="Test A", status="do_zaplaty"):
        plik = self.root / f"{numer}.pdf"
        plik.write_text(f"%PDF-1.4\n% Syntetyczny {numer}\n%%EOF", encoding="ascii")
        dok, _ = self.rejestr.importuj_pdf(plik)
        return self.rejestr.zapisz_rachunek(DaneRachunku(
            dokument_id=dok, dostawca=dostawca, numer=numer, kwota=kwota,
            kategoria_id=self.gaz, okres_do=usluga, data_wystawienia=wystawiono, status=status,
        ))


class TestStatystyki(BazaStatystyk):
    def test_usluga_i_faktyczne_platnosci_maja_rozne_miesiace(self):
        pazdziernik = self.faktura("starsza", "15,01", usluga="2026-10-31")
        listopad = self.faktura("pozniejsza", "18,18")
        self.faktura("brak-daty-oplacenia", "9,05", status="oplacony")
        nieoplacona = self.faktura("nieoplacona", "3,03")
        self.db.execute("UPDATE rachunki SET okres_do='' WHERE id=?", (nieoplacona,))
        self.faktura("bez-dat", "77,77", wystawiono="")
        self.finanse.ustaw_oplacona(pazdziernik, "2026-11-01")
        self.finanse.ustaw_oplacona(listopad, "2026-12-01")
        wycofana = self.faktura("wycofana", "99,99")
        self.finanse.ustaw_oplacona(wycofana, "2026-11-30")
        self.finanse.wycofaj(wycofana, powod="Test")

        zmiany = self.db.total_changes
        raport = self.stat.zestawienie(LISTOPAD)
        self.assertEqual(raport.biezacy.razem, 3026)
        self.assertEqual(raport.biezacy.oplacone, 2723)
        self.assertEqual(raport.biezacy.do_zaplaty, 303)
        self.assertEqual(raport.biezacy.liczba, 3)
        self.assertEqual(raport.poprzedni.razem, 1501)
        platnosci = self.stat.zestawienie(LISTOPAD, podstawa="platnosc")
        self.assertEqual(platnosci.biezacy.razem, 1501)
        self.assertEqual(platnosci.biezacy.do_zaplaty, 0)
        historia = HistoriaRozliczen(self.db).sumy_miesiaca("2026-11")
        self.assertEqual(historia["billed_grosze"], raport.biezacy.razem)
        self.assertEqual(historia["payments_in_month_grosze"], platnosci.biezacy.razem)
        self.assertEqual(self.db.total_changes, zmiany)

    def test_filtry_kategorii_dostawcy_i_statusu_z_faktura_wielopozycyjna(self):
        ident = self.faktura("dzielona", "100,01")
        self.db.execute(
            "UPDATE pozycje_rachunku SET kwota_grosze=4001 WHERE rachunek_id=?", (ident,)
        )
        self.db.executemany(
            "INSERT INTO pozycje_rachunku(rachunek_id,kategoria_id,kwota_grosze) VALUES (?,?,?)",
            [(ident, self.prad, 1500), (ident, self.prad, 4500)],
        )
        self.faktura("inna", "20,00", dostawca="Test B", status="oplacony")
        raport = self.stat.zestawienie(LISTOPAD)
        self.assertEqual(raport.biezacy.razem, 12001)
        self.assertEqual(raport.biezacy.liczba, 2)
        self.assertEqual(raport.kategorie[self.gaz].razem, 6001)
        self.assertEqual(raport.kategorie[self.prad].razem, 6000)
        self.assertEqual(raport.kategorie[self.prad].liczba, 1)
        self.assertEqual(raport.dostawcy["Test A"].razem, 10001)
        filtrowany = self.stat.zestawienie(
            LISTOPAD, kategoria=self.prad, dostawca="Test A", status="do_zaplaty"
        )
        self.assertEqual(filtrowany.biezacy.razem, 6000)
        self.assertEqual(filtrowany.dostawcy["Test A"].razem, 6000)
        self.assertEqual(self.stat.zestawienie(LISTOPAD, status="oplacony").biezacy.razem, 2000)
        self.assertEqual(self.stat.zestawienie(LISTOPAD, dostawca="brak").biezacy.liczba, 0)

    def test_niepelne_i_niespojne_pozycje_zachowuja_kwote_naglowka(self):
        czesciowa = self.faktura("czesciowa", "10,00")
        bez_pozycji = self.faktura("bez-pozycji", "3,00")
        nadmiar = self.faktura("nadmiar", "2,00")
        self.db.execute(
            "UPDATE pozycje_rachunku SET kwota_grosze=700 WHERE rachunek_id=?", (czesciowa,)
        )
        self.db.execute("DELETE FROM pozycje_rachunku WHERE rachunek_id=?", (bez_pozycji,))
        self.db.execute(
            "UPDATE pozycje_rachunku SET kwota_grosze=999 WHERE rachunek_id=?", (nadmiar,)
        )
        raport = self.stat.zestawienie(LISTOPAD)
        self.assertEqual(raport.biezacy.razem, 1500)
        self.assertEqual(raport.kategorie[self.gaz].razem, 700)
        self.assertEqual(raport.kategorie[BEZ_KATEGORII].razem, 800)
        self.assertEqual(self.stat.zestawienie(LISTOPAD, kategoria=BEZ_KATEGORII).biezacy.razem, 800)

    def test_grupowanie_i_porownanie_kalendarzowe(self):
        self.faktura("2025", "20,50", wystawiono="2025-02-01")
        self.faktura("2026-styczen", "11,10", wystawiono="2026-01-01")
        self.faktura("2026-grudzien", "5,05", wystawiono="2026-12-31")
        rok = ZakresDat(date(2026, 1, 1), date(2026, 12, 31))
        raport = self.stat.zestawienie(rok, grupowanie="rok")
        self.assertEqual(raport.okresy["2026"].razem, 1615)
        self.assertEqual(raport.poprzedni.razem, 2050)
        self.assertEqual(raport.poprzedni_zakres, ZakresDat(date(2025, 1, 1), date(2025, 12, 31)))
        self.assertEqual(set(self.stat.zestawienie(rok).okresy), {"2026-01", "2026-12"})
        luty = ZakresDat(date(2024, 2, 1), date(2024, 2, 29))
        self.assertEqual(luty.poprzedni(), ZakresDat(date(2024, 1, 1), date(2024, 1, 31)))
        krotki = ZakresDat(date(2026, 3, 1), date(2026, 3, 2))
        self.assertEqual(krotki.poprzedni(), ZakresDat(date(2026, 2, 27), date(2026, 2, 28)))
        with self.assertRaises(ValueError):
            ZakresDat(date(2026, 3, 1), date(2026, 2, 1))


class TestWidokStatystyk(BazaStatystyk):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def okno(self):
        self.addCleanup(set_language, current_language())
        self.enterContext(patch.object(ustawienia, "path_settings",
                                       return_value=self.root / "prefs.json"))
        self.enterContext(patch("gui.statystyki.today_warsaw", return_value="2026-11-16"))
        ustawienia.save({"language": "pl"})
        okno = OknoGlowne(self.rejestr)
        okno.show()
        okno._agent_timer.stop()
        self.addCleanup(okno.close)
        okno.nawigacja_glowna["statistics"].click()
        self.app.processEvents()
        return okno

    def test_pusty_widok_bledny_zakres_i_powrot(self):
        okno = self.okno()
        widok = okno.statystyki
        self.assertIs(okno.moduly.currentWidget(), widok)
        self.assertTrue(okno.nawigacja_glowna["statistics"].isChecked())
        self.assertTrue(widok.komunikat.isVisible())
        self.assertEqual(widok.karty["total"][1].text(), "0,00 zł")
        widok.od.setDate(QDate(2026, 12, 1))
        self.assertIn("Data początkowa", widok.komunikat.text())
        self.assertEqual(widok.karty["total"][1].text(), "—")
        widok.btn_rok.click()
        self.assertEqual(widok.grupowanie.currentData(), "rok")
        self.assertEqual(widok.od.date(), QDate(2026, 1, 1))
        self.assertEqual(widok.do.date(), QDate(2026, 12, 31))
        widok.btn_miesiac.click()
        self.assertEqual(widok.grupowanie.currentData(), "miesiac")
        self.assertEqual(widok.karty["total"][1].text(), "0,00 zł")

    def test_wykresy_filtry_i_tlumaczenie_zachowuja_wybor(self):
        ident = self.faktura("oplacona", "15,25")
        self.finanse.ustaw_oplacona(ident, "2026-12-01")
        self.faktura("nieoplacona", "30,21", dostawca="Test B")
        okno = self.okno()
        widok = okno.statystyki
        self.assertEqual(widok.karty["total"][1].text(), "45,46 zł")
        self.assertEqual(widok.tabele["suppliers"].rowCount(), 2)
        self.assertEqual(widok.tabele["suppliers"].item(0, 0).text(), "Test B")
        self.assertEqual(widok.tabele["suppliers"].cellWidget(0, 1).value(), 1000)
        widok.kategoria.setCurrentIndex(widok.kategoria.findData(self.gaz))
        widok.dostawca.setCurrentIndex(widok.dostawca.findData("Test B"))
        widok.status.setCurrentIndex(widok.status.findData("do_zaplaty"))
        widok.zakladki.setCurrentIndex(1)
        okno.change_language("en")
        self.assertEqual(widok.kategoria.currentText(), "Gas")
        self.assertEqual(widok.kategoria.currentData(), self.gaz)
        self.assertEqual(widok.dostawca.currentData(), "Test B")
        self.assertEqual(widok.status.currentData(), "do_zaplaty")
        self.assertEqual(widok.zakladki.tabText(1), "Categories")
        self.assertEqual(widok.karty["total"][1].text(), "30,21 PLN")
        widok.podstawa.setCurrentIndex(widok.podstawa.findData("platnosc"))
        self.assertEqual(widok.karty["total"][1].text(), "0,00 PLN")
        self.assertFalse(widok.status.isEnabled())
        self.assertEqual(widok.status.currentData(), "oplacony")
        widok.podstawa.setCurrentIndex(widok.podstawa.findData("usluga"))
        self.assertEqual(widok.status.currentData(), "do_zaplaty")
        self.assertTrue(widok.status.isEnabled())
        self.assertEqual(widok.karty["total"][1].text(), "30,21 PLN")
        okno.nawigacja_glowna["dashboard"].click()
        self.faktura("nastepna", "1,00", dostawca="Test B")
        okno.nawigacja_glowna["statistics"].click()
        self.assertEqual(widok.karty["total"][1].text(), "31,21 PLN")
        self.assertEqual(widok.zakladki.currentIndex(), 1)
