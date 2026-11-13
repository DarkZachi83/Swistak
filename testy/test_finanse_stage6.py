# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 6: historia, oczekiwania, świadome zamknięcie i dialog Qt.

Wszystkie faktury, firmy i pliki są w całości syntetyczne.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import ustawienia
from gui.dialog_plan_historia import DialogPlanHistoria, FormularzProfilu, chosen_id
from gui.okno_glowne import OknoGlowne
from uslugi.finanse import Finanse
from uslugi.historia import HistoriaRozliczen
from uslugi.plan_rachunkow import PlanRachunkow
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class FinanceStage6Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.registry=RejestrRachunkow(self.root / "dane")
        self.db=self.registry.db
        self.finance=Finanse(self.db)
        self.plan=PlanRachunkow(self.db)
        self.history=HistoriaRozliczen(self.db)
        self.category=int(self.registry.kategorie()[0]["id"])
        self.invoices=[]
        for i,(amount,status) in enumerate([("180,00","do_zaplaty"),("120,00","do_zaplaty")],1):
            pdf=self.root / f"FAKTYCZNIE-FIKCYJNA-{i}.pdf"
            pdf.write_bytes(f"%PDF-1.4\n%Fikcyjny rachunek {i}\n%%EOF".encode())
            doc,_=self.registry.importuj_pdf(pdf)
            ident=self.registry.zapisz_rachunek(DaneRachunku(
                dokument_id=doc,dostawca=f"Dostawca DEMO {i}",numer=f"TEST-{i}",
                kwota=amount,kategoria_id=self.category,
                data_wystawienia="2026-11-01",termin_platnosci="2026-11-05",
                okres_od="2026-10-01",okres_do="2026-10-31",status=status,
            ))
            self.invoices.append(ident)

    def tearDown(self):
        self.registry.zamknij()
        self.temp.cleanup()


class TestHistoriaEtap6(FinanceStage6Fixture):
    def test_miesiace_i_sumy_rozliczeniowe_nie_mieszaja_wystawienia_z_oplaceniem(self):
        self.finance.ustaw_oplacona(self.invoices[0],"2026-11-09")
        october=self.history.miesiac("2026-10",dzisiaj="2026-11-13")
        self.assertEqual(october["billed_grosze"],30000)
        self.assertEqual(october["paid_service_grosze"],18000)
        self.assertEqual(october["unpaid_grosze"],12000)
        self.assertEqual(october["payments_in_month_grosze"],0)
        november=self.history.miesiac("2026-11",dzisiaj="2026-11-13")
        self.assertEqual(november["payments_in_month_grosze"],18000)
        self.assertEqual(november["billed_grosze"],0)
        self.assertIn("2026-10",self.history.miesiace())
        self.assertIn("2026-11",self.history.miesiace())

    def test_wycofanie_zachowuje_fakture_w_historii_ale_nie_w_sumach(self):
        self.finance.wycofaj(self.invoices[0],powod="Fikcyjny duplikat")
        state=self.history.miesiac("2026-10",dzisiaj="2026-11-13")
        self.assertEqual(state["billed_grosze"],12000)
        self.assertEqual(state["withdrawn_count"],1)
        rows=self.history.faktury("2026-10")
        self.assertEqual(len(rows),2)
        self.assertEqual(sum(bool(row["wycofano_utc"]) for row in rows),1)
        self.finance.przywroc(self.invoices[0],powod="Przywracamy test")
        self.assertEqual(self.history.miesiac("2026-10")["billed_grosze"],30000)

    def test_dziennik_pokazuje_platnosc_i_zamkniecie_bez_danych_ocr(self):
        self.finance.ustaw_oplacona(self.invoices[0],"2026-11-09")
        self.finance.potwierdz_kompletnosc("2026-10",dzisiaj="2026-11-13")
        events=self.history.dziennik_miesiaca("2026-10")
        self.assertIn("oplacenie",[r["operacja"] for r in events])
        self.assertIn("potwierdzenie_kompletnosci",[r["operacja"] for r in events])
        self.assertTrue(all("przed_json" not in r and "po_json" not in r for r in events))

    def test_dziennik_platnosci_i_zmian_profilu_zawiera_miesiac_wplywu(self):
        profile=self.plan.utworz_profil("Gaz DEMO",cykl_od="2026-10")
        self.finance.ustaw_oplacona(self.invoices[0],"2026-11-09")
        october=self.history.dziennik_miesiaca("2026-10")
        november=self.history.dziennik_miesiaca("2026-11")
        self.assertIn("utworzenie",[x["operacja"] for x in october])
        self.assertIn("oplacenie",[x["operacja"] for x in november])
        self.plan.ustaw_aktywnosc(profile,False,powod="Wyłączono DEMO")
        self.assertIn("zmiana_aktywnosci",[
            x["operacja"] for x in self.history.dziennik_miesiaca("2026-10")
        ])

    def test_unresolved_future_blocks_completeness_before_expected_date(self):
        profile=self.plan.utworz_profil(
            "Fikcyjny internet",cykl_od="2026-10",przesuniecie_dni=35
        )
        ids=self.plan.generuj_oczekiwania("2026-10")
        self.assertEqual(len(ids),1)
        self.assertEqual(self.history.oczekiwania(
            "2026-10",dzisiaj="2026-11-13"
        )[0]["state"],"waiting")
        self.assertEqual(self.finance.ocena_cyklu(
            "2026-10",dzisiaj="2026-11-13"
        )["missing_expected"],0)
        self.assertEqual(self.finance.ocena_cyklu(
            "2026-10",dzisiaj="2026-11-13"
        )["unresolved_expected"],1)
        with self.assertRaisesRegex(ValueError,"brakujące"):
            self.finance.potwierdz_kompletnosc("2026-10",dzisiaj="2026-11-13")
        self.plan.oznacz_wyjatek(ids[0],typ="nie_wystawiono",
                                powod="Otrzymano potwierdzenie dostawcy")
        self.finance.potwierdz_kompletnosc("2026-10",dzisiaj="2026-11-13")
        self.assertTrue(self.finance.ocena_cyklu("2026-10")["documents_confirmed"])
        self.assertFalse(self.finance.ocena_cyklu("2026-10")["closed"])
        self.assertEqual(profile,1)

    def test_cofniecie_wyjatku_uniewaznia_potwierdzenie_i_zostawia_audyt(self):
        self.plan.utworz_profil("DEMO gaz",cykl_od="2026-10")
        expected=self.plan.generuj_oczekiwania("2026-10")[0]
        self.plan.oznacz_wyjatek(expected,typ="nie_wystawiono",powod="DEMO potwierdziło")
        self.finance.potwierdz_kompletnosc("2026-10",dzisiaj="2026-11-13")
        self.plan.anuluj_wyjatek(expected,powod="Pojawiły się nowe dane")
        self.assertFalse(self.finance.ocena_cyklu("2026-10")["documents_confirmed"])
        self.assertEqual(self.history.oczekiwania(
            "2026-10",dzisiaj="2026-11-13"
        )[0]["state"],"missing")
        self.assertIn("cofniecie_wyjatku",[
            x["operacja"] for x in self.finance.dziennik("expectation",expected)
        ])

    def test_powiazanie_faktury_z_innym_cyklem_zablokowane(self):
        self.plan.utworz_profil("Testowy fundusz",cykl_od="2026-10")
        expected=self.plan.generuj_oczekiwania("2026-10")[0]
        pdf=self.root/"INNY-OKRES.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%Inny okres\n%%EOF")
        doc,_=self.registry.importuj_pdf(pdf)
        invoice=self.registry.zapisz_rachunek(DaneRachunku(
            dokument_id=doc,dostawca="Firma TEST",numer="INNE/11",
            kwota="10,00",kategoria_id=self.category,
            okres_od="2026-11-01",okres_do="2026-11-30",
        ))
        with self.assertRaisesRegex(ValueError,"innym miesiącem"):
            self.plan.powiaz(expected,invoice)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM powiazania_oczekiwanych"
        ).fetchone()[0],0)
        self.plan.powiaz(expected,self.invoices[0])
        self.assertEqual(self.history.oczekiwania("2026-10")[0]["state"],"received")

    def test_profil_wstrzymanie_wznowienie_bez_utraty_historii(self):
        profile=self.plan.utworz_profil("TEST Telefon",cykl_od="2026-10")
        self.plan.generuj_oczekiwania("2026-10")
        self.plan.ustaw_aktywnosc(profile,False,powod="Zawieszona usługa")
        self.assertEqual(self.plan.generuj_oczekiwania("2026-11"),[])
        self.assertEqual(len(self.history.oczekiwania("2026-10")),1)
        self.plan.ustaw_aktywnosc(profile,True,powod="Wznowiono usługę")
        self.assertEqual(len(self.plan.generuj_oczekiwania("2026-11")),1)
        self.assertIn("zmiana_aktywnosci",[
            r["operacja"] for r in self.finance.dziennik("profile",profile)
        ])

    def test_miesiac_potwierdzony_dokumentami_nadal_nieoplacony(self):
        self.finance.potwierdz_kompletnosc("2026-10",dzisiaj="2026-11-13")
        state=self.history.miesiac("2026-10",dzisiaj="2026-11-13")
        self.assertTrue(state["documents_confirmed"])
        self.assertFalse(state["closed"])
        self.finance.ustaw_oplacona(self.invoices[0],"2026-11-10")
        self.finance.ustaw_oplacona(self.invoices[1],"2026-11-12")
        self.assertTrue(self.history.miesiac("2026-10",dzisiaj="2026-11-13")["closed"])


class TestGUIEtap6(FinanceStage6Fixture):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_dialog_ma_trzy_karty_i_sam_odczyt_nie_zapisuje(self):
        before=self.db.execute("SELECT COUNT(*) FROM dziennik_zdarzen").fetchone()[0]
        dialog=DialogPlanHistoria(self.registry)
        self.assertEqual(dialog.tabs.count(),3)
        self.assertEqual(dialog.month.objectName(),"planSelectedMonth")
        self.assertEqual(dialog.confirm_btn.objectName(),"confirmMonthCompleteness")
        dialog.month.setCurrentText("2026-10")
        self.assertEqual(dialog.history_invoices.rowCount(),2)
        self.assertEqual(dialog.profiles.rowCount(),0)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM dziennik_zdarzen"
        ).fetchone()[0],before)
        dialog.close()

    def test_karta_planu_widzi_profil_i_nie_tworzony_automatycznie_rachunek(self):
        self.plan.utworz_profil("DEMO Energia",cykl_od="2026-10")
        dialog=DialogPlanHistoria(self.registry)
        dialog.month.setCurrentText("2026-10")
        self.assertEqual(dialog.profiles.rowCount(),1)
        self.assertEqual(dialog.expected.rowCount(),0)
        with patch("gui.dialog_plan_historia.confirm",return_value=True):
            dialog._generate()
        self.assertEqual(dialog.expected.rowCount(),1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM rachunki"
        ).fetchone()[0],2)
        dialog.close()

    def test_razem_ze_zmiana_stanu_odswieza_agent_i_przekazuje_invoice_id(self):
        dialog=DialogPlanHistoria(self.registry)
        dialog.month.setCurrentText("2026-10")
        received=[]
        dialog.daneZmienione.connect(received.append)
        dialog.history_invoices.selectRow(0)
        selected=dialog._invoice()
        self.assertIsNotNone(selected)
        self.assertEqual(chosen_id(dialog.history_invoices),selected["id"])
        with patch("gui.dialog_plan_historia.QDialog.exec",
                   return_value=QDialog.DialogCode.Accepted),patch(
                   "gui.dialog_plan_historia.confirm",return_value=True):
            dialog._paid()
        self.assertEqual(received[-1],selected["id"])
        self.assertEqual(self.db.execute(
            "SELECT status FROM rachunki WHERE id=?",(selected["id"],)
        ).fetchone()[0],"oplacony")
        self.assertGreater(self.db.execute(
            "SELECT COUNT(*) FROM dziennik_zdarzen WHERE operacja='oplacenie'"
        ).fetchone()[0],0)
        dialog.close()

    def test_odmowa_potwierdzenia_miesiaca_nie_powoduje_zapisu(self):
        dialog=DialogPlanHistoria(self.registry)
        dialog.month.setCurrentText("2026-10")
        before=self.db.execute(
            "SELECT COUNT(*) FROM cykle_rozliczeniowe"
        ).fetchone()[0]
        with patch("gui.dialog_plan_historia.confirm",return_value=False):
            dialog._confirm_month()
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cykle_rozliczeniowe"
        ).fetchone()[0],before)
        dialog.close()

    def test_zamkniecie_wymaga_zgody_i_zachowuje_nieoplacenie(self):
        dialog=DialogPlanHistoria(self.registry)
        dialog.month.setCurrentText("2026-10")
        received=[]
        dialog.daneZmienione.connect(received.append)
        with patch("gui.dialog_plan_historia.confirm",return_value=True):
            dialog._confirm_month()
        self.assertTrue(self.finance.ocena_cyklu(
            "2026-10",dzisiaj="2026-11-13"
        )["documents_confirmed"])
        self.assertFalse(self.finance.ocena_cyklu(
            "2026-10",dzisiaj="2026-11-13"
        )["closed"])
        self.assertEqual(received, [None])
        dialog.close()

    def test_nowy_profil_wymaga_potwierdzenia_i_potem_widoczny_w_tabeli(self):
        dialog=DialogPlanHistoria(self.registry)
        values={
            "nazwa":"Nowy syntetyczny profil",
            "dostawca":"Dostawca testowy",
            "kategoria_id":self.category,
            "typ":"miesieczny",
            "co_ile_miesiecy":1,
            "cykl_od":"2026-11",
            "cykl_kotwicy":"2026-11",
            "przesuniecie_dni":0,
        }
        with patch.object(FormularzProfilu,"exec",
                          return_value=QDialog.DialogCode.Accepted),patch.object(
                          FormularzProfilu,"values",return_value=values),patch(
                          "gui.dialog_plan_historia.confirm",return_value=True):
            dialog._create_profile()
        self.assertEqual(dialog.profiles.rowCount(),1)
        self.assertEqual(dialog.profiles.item(0,0).text(),values["nazwa"])
        dialog.close()

    def test_main_utrzymuje_szesc_etapow_i_ma_wejscie_plan_history(self):
        root=self.root
        with patch.object(ustawienia,"path_settings",return_value=root/"settings.json"):
            ustawienia.save({"language":"pl","ollama_model":"demo"})
            window=OknoGlowne(self.registry)
            self.assertEqual(window.nawigacja.count(),6)
            self.assertEqual(window.btn_plan_historia.objectName(),"otworzPlanHistoria")
            self.assertEqual(window.akcja_plan_historia.text(),"Plan rachunków i Historia")
            with patch("gui.okno_glowne.DialogPlanHistoria.exec",
                       return_value=QDialog.DialogCode.Rejected):
                window._open_plan_historia()
            window.close()


if __name__=="__main__":
    unittest.main()
