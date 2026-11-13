# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 3: rozliczenia i harmonogramy na wyłącznie syntetycznej bazie."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from baza.migracje import zastosuj_migracje
from baza.polaczenie import polacz
from uslugi.finanse import Finanse
from uslugi.plan_rachunkow import PlanRachunkow
from uslugi.rachunki import DaneRachunku, RejestrRachunkow
from uslugi.kopie_zapasowe import utworz_kopie, przygotuj_przywracanie
from ai_core.gateway import ToolGateway


class TestFinanseEtap3(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.rejestr = RejestrRachunkow(self.home / "dane")
        self.db = self.rejestr.db
        self.finanse = Finanse(self.db)
        self.plan = PlanRachunkow(self.db)
        self.category = int(self.rejestr.kategorie()[0]["id"])
        self.pdf = self.home / "fikcyjna.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n%Tylko fikcyjna faktura\n%%EOF")
        self.doc, _ = self.rejestr.importuj_pdf(self.pdf)

    def tearDown(self):
        self.rejestr.zamknij()
        self.tmp.cleanup()

    def invoice(self, **overrides):
        data = {
            "dokument_id": self.doc, "dostawca": "Firma Syntetyczna",
            "numer": "FAKE/10/2026", "kwota": "180,00",
            "kategoria_id": self.category,
            "okres_od": "2026-10-01", "okres_do": "2026-10-31",
            "data_wystawienia": "2026-11-02",
            "termin_platnosci": "2026-11-05",
        }
        data.update(overrides)
        return DaneRachunku(**data)

    def task(self, gateway, allowed, task_id="financial"):
        return {
            "contract_version":"1.0","task_id":task_id,"role":"main",
            "instruction":"Zwróć kontrolowane dane testowe","context":{"reference_date":"2026-11-13"},
            "allowed_tools":list(allowed),"response_schema":"AnalysisResult",
            "data_revision":gateway.revision(),"locale":"pl","timezone":"Europe/Warsaw",
            "limits":{"max_steps":6,"timeout_ms":15000,"max_records":100},
        }

    def run_tool(self, session, name, params, cid):
        return session.execute({
            "contract_version":"1.0","task_id":session.task["task_id"],
            "call_id":cid,"tool_name":name,"tool_version":"1.0",
            "arguments":params,"data_revision":session.task["data_revision"],
        })

    def test_schemat_migracje_pieciu_wersji_i_kontrola_kluczy(self):
        names=[r["nazwa"] for r in self.db.execute("SELECT nazwa FROM migracje ORDER BY nazwa")]
        self.assertEqual(len(names),5)
        self.assertTrue(names[2].startswith("003_"))
        self.assertEqual(self.db.execute("PRAGMA quick_check").fetchone()[0],"ok")
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(),[])
        for name in ("profile_rachunkow","harmonogramy_rachunkow",
                     "oczekiwane_dokumenty","powiazania_oczekiwanych",
                     "cykle_rozliczeniowe","dziennik_zdarzen"):
            self.assertIsNotNone(self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",(name,)
            ).fetchone())

    def test_oplacenie_dziennik_data_i_bez_nadpisania(self):
        ident = self.rejestr.zapisz_rachunek(self.invoice())
        version = self.db.execute("SELECT wersja_rekordu FROM rachunki WHERE id=?",(ident,)).fetchone()[0]
        self.finanse.ustaw_oplacona(ident,"2026-11-09",expected_version=version)
        self.assertEqual(self.rejestr.rachunek(self.doc)["data_oplacenia"],"2026-11-09")
        self.assertEqual(self.rejestr.rachunek(self.doc)["status"],"oplacony")
        # Formularz OCR przekazuje nieświadomie status do_zaplaty:
        self.rejestr.zapisz_rachunek(
            self.invoice(status="do_zaplaty"),nadpisz_id=ident,
        )
        final=self.rejestr.rachunek(self.doc)
        self.assertEqual(final["status"],"oplacony")
        self.assertEqual(final["data_oplacenia"],"2026-11-09")
        self.assertGreater(final["wersja_rekordu"],version)
        events=self.finanse.dziennik("invoice",ident)
        self.assertIn("oplacenie",[x["operacja"] for x in events])
        for row in events:
            self.assertNotIn("numer_konta",row["przed_json"] or "")
            self.assertNotIn("numer_konta",row["po_json"] or "")
        self.finanse.cofnij_oplacenie(ident,powod="Test świadomej korekty")
        self.assertIsNone(self.rejestr.rachunek(self.doc)["data_oplacenia"])
        self.assertEqual(self.rejestr.rachunek(self.doc)["status"],"do_zaplaty")

    def test_oplacona_zmiana_kwoty_wymaga_potwierdzenia(self):
        ident=self.rejestr.zapisz_rachunek(self.invoice())
        self.finanse.ustaw_oplacona(ident,"2026-11-09")
        with self.assertRaisesRegex(ValueError,"osobnego potwierdzenia"):
            self.rejestr.zapisz_rachunek(
                self.invoice(kwota="220,00"),nadpisz_id=ident
            )
        self.assertEqual(self.rejestr.rachunek(self.doc)["kwota_grosze"],18000)
        self.rejestr.zapisz_rachunek(
            self.invoice(kwota="220,00"),nadpisz_id=ident,
            potwierdz_korekte_oplaconej=True,
        )
        self.assertEqual(self.rejestr.rachunek(self.doc)["kwota_grosze"],22000)
        self.assertEqual(self.rejestr.rachunek(self.doc)["data_oplacenia"],"2026-11-09")

    def test_wycofanie_przywrocenie_zachowuje_pdf_i_status(self):
        ident=self.rejestr.zapisz_rachunek(self.invoice())
        self.finanse.ustaw_oplacona(ident,"2026-11-09")
        pdf_bytes=self.rejestr.sciezka_pdf(self.doc).read_bytes()
        self.finanse.wycofaj(ident,powod="Fikcyjny duplikat")
        self.assertEqual(self.rejestr.faktury(),[])
        with self.assertRaisesRegex(ValueError,"wycofana"):
            self.rejestr.zapisz_rachunek(self.invoice(),nadpisz_id=ident)
        with self.assertRaises(ValueError):
            self.finanse.ustaw_oplacona(ident,"2026-11-10")
        self.finanse.przywroc(ident,powod="Odzyskano prawidłową fakturę")
        self.assertEqual(len(self.rejestr.faktury()),1)
        self.assertEqual(self.rejestr.rachunek(self.doc)["id"],ident)
        self.assertEqual(self.rejestr.rachunek(self.doc)["data_oplacenia"],"2026-11-09")
        self.assertEqual(self.rejestr.sciezka_pdf(self.doc).read_bytes(),pdf_bytes)
        self.assertIn("przywrocenie",[e["operacja"] for e in self.finanse.dziennik("invoice",ident)])

    def test_wersja_rekordu_chroni_przed_starym_formularzem(self):
        ident=self.rejestr.zapisz_rachunek(self.invoice())
        with self.assertRaisesRegex(ValueError,"odśwież"):
            self.finanse.ustaw_oplacona(ident,"2026-11-09",expected_version=999)
        self.assertEqual(self.rejestr.rachunek(self.doc)["status"],"do_zaplaty")

    def test_plan_oczekiwanie_poczatek_nastepnego_miesiaca(self):
        profile=self.plan.utworz_profil(
            "Telefon prywatny",dostawca="Operator Syntetyczny",
            cykl_od="2026-10",typ="miesieczny"
        )
        self.assertEqual(self.plan.generuj_oczekiwania("2026-09"),[])
        generated=self.plan.generuj_oczekiwania("2026-10")
        self.assertEqual(len(generated),1)
        self.assertEqual(self.plan.generuj_oczekiwania("2026-10"),[])
        row=self.db.execute(
            "SELECT oczekiwany_od FROM oczekiwane_dokumenty WHERE id=?",(generated[0],)
        ).fetchone()
        self.assertEqual(row["oczekiwany_od"],"2026-11-01")
        gateway=ToolGateway(self.rejestr.katalog/"swistak.sqlite3")
        task=self.task(gateway,["plan.expected"],"plan-check")
        with gateway.session(task) as session:
            result=self.run_tool(session,"plan.expected",{"cycle":"2026-10"},"plan")
            self.assertEqual(result["status"],"ok")
            self.assertEqual(result["data"]["expected"][0]["status"],"brak")
        self.assertEqual(profile,1)

    def test_wyjatki_dokumentowe_nie_tworza_faktur(self):
        self.plan.utworz_profil("Niedostarczony rachunek",cykl_od="2026-10")
        expectation=self.plan.generuj_oczekiwania("2026-10")[0]
        evaluation=self.finanse.ocena_cyklu("2026-10",dzisiaj="2026-11-13")
        self.assertEqual(evaluation["missing_expected"],1)
        with self.assertRaisesRegex(ValueError,"brakujące"):
            self.finanse.potwierdz_kompletnosc("2026-10",brak_rachunkow=True,
                                              dzisiaj="2026-11-13")
        self.plan.oznacz_wyjatek(expectation,typ="nie_wystawiono",powod="Dostawca nie wystawił")
        self.finanse.potwierdz_kompletnosc("2026-10",brak_rachunkow=True,
                                          dzisiaj="2026-11-13")
        self.assertTrue(self.finanse.ocena_cyklu("2026-10",dzisiaj="2026-11-13")["closed"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0],0)

    def test_plan_powiazania_z_wieloma_fakturami(self):
        self.plan.utworz_profil("Gaz",cykl_od="2026-10")
        expected=self.plan.generuj_oczekiwania("2026-10")[0]
        first=self.rejestr.zapisz_rachunek(self.invoice())
        other_pdf=self.home/"drugi.pdf"
        other_pdf.write_bytes(b"%PDF-1.4\n%drugi syntetyczny\n%%EOF")
        second_doc,_=self.rejestr.importuj_pdf(other_pdf)
        second=self.rejestr.zapisz_rachunek(self.invoice(
            dokument_id=second_doc,numer="FAKE/10/2026-B",kwota="20,00"))
        self.plan.powiaz(expected,first)
        self.plan.powiaz(expected,second)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM powiazania_oczekiwanych WHERE oczekiwany_id=?",
            (expected,)).fetchone()[0],2)
        gateway=ToolGateway(self.rejestr.katalog/"swistak.sqlite3")
        task=self.task(gateway,["plan.expected","plan.match"],"matched")
        with gateway.session(task) as session:
            rows=self.run_tool(session,"plan.expected",{"cycle":"2026-10"},"expected")
            self.assertEqual(rows["data"]["expected"][0]["status"],"otrzymano")
            matches=self.run_tool(session,"plan.match",{"invoice_id":first},"match")
            self.assertTrue(matches["data"]["candidates"][0]["linked"])

    def test_kompletnosc_nie_jest_rowna_oplaceniu(self):
        ident=self.rejestr.zapisz_rachunek(self.invoice())
        self.finanse.potwierdz_kompletnosc("2026-10",dzisiaj="2026-11-13")
        assessment=self.finanse.ocena_cyklu("2026-10",dzisiaj="2026-11-13")
        self.assertTrue(assessment["documents_confirmed"])
        self.assertFalse(assessment["closed"])
        self.finanse.ustaw_oplacona(ident,"2026-11-09")
        assessment=self.finanse.ocena_cyklu("2026-10",dzisiaj="2026-11-13")
        self.assertTrue(assessment["closed"])
        self.finanse.cofnij_oplacenie(ident,powod="Przez pomyłkę")
        assessment=self.finanse.ocena_cyklu("2026-10",dzisiaj="2026-11-13")
        self.assertTrue(assessment["documents_confirmed"])
        self.assertFalse(assessment["closed"])

    def test_przypisanie_nowej_faktury_uniewaznia_kompletnosc(self):
        self.finanse.potwierdz_kompletnosc(
            "2026-10",brak_rachunkow=True,dzisiaj="2026-11-13",
        )
        self.assertTrue(self.finanse.ocena_cyklu("2026-10",dzisiaj="2026-11-13")["closed"])
        self.rejestr.zapisz_rachunek(self.invoice())
        state=self.finanse.ocena_cyklu("2026-10",dzisiaj="2026-11-13")
        self.assertFalse(state["documents_confirmed"])
        self.assertFalse(state["closed"])
        self.assertIn("uniewaznienie_kompletnosci",
                      [e["operacja"] for e in self.finanse.dziennik("cycle","2026-10")])

    def test_wersjonowane_harmonogramy_nie_nadpisuja_starych(self):
        profile=self.plan.utworz_profil(
            "Energia",cykl_od="2026-09",typ="co_n_miesiecy",
            co_ile_miesiecy=2,cykl_kotwicy="2026-09",
        )
        self.assertEqual(len(self.plan.generuj_oczekiwania("2026-09")),1)
        self.assertEqual(self.plan.generuj_oczekiwania("2026-10"),[])
        next_version=self.plan.zmien_harmonogram(
            profile,cykl_od="2026-11",typ="miesieczny",
        )
        self.assertEqual(next_version,2)
        self.assertEqual(len(self.plan.generuj_oczekiwania("2026-11")),1)
        versions=list(self.db.execute(
            "SELECT wersja,typ,cykl_od,cykl_do FROM harmonogramy_rachunkow "
            "WHERE profil_id=? ORDER BY wersja",(profile,)
        ))
        self.assertEqual(versions[0]["cykl_do"],"2026-10")
        self.assertEqual(versions[1]["cykl_od"],"2026-11")

    def test_gateway_audyt_daty_i_cykl(self):
        ident=self.rejestr.zapisz_rachunek(self.invoice())
        self.finanse.ustaw_oplacona(ident,"2026-11-09")
        self.finanse.potwierdz_kompletnosc("2026-10",dzisiaj="2026-11-13")
        gateway=ToolGateway(self.rejestr.katalog/"swistak.sqlite3")
        task=self.task(gateway,["cycle.evaluate","audit.read","finance.aggregate"],"audit")
        with gateway.session(task) as session:
            cycle=self.run_tool(session,"cycle.evaluate",{"cycle":"2026-10"},"cyc")
            self.assertTrue(cycle["data"]["closed"])
            audit=self.run_tool(session,"audit.read",{
                "entity_type":"invoice","entity_id":str(ident)},"history")
            self.assertGreaterEqual(len(audit["data"]["events"]),2)
            paid=self.run_tool(session,"finance.aggregate",{
                "basis":"paid_date","period_from":"2026-11-01",
                "period_to":"2026-11-30","group_by":"month"
            },"paid")
            self.assertEqual(paid["data"]["total_grosze"],18000)

    def test_backup_przenosi_historie_i_profile(self):
        ident=self.rejestr.zapisz_rachunek(self.invoice())
        self.plan.utworz_profil("Zobowiązanie DEMO",cykl_od="2026-10")
        self.finanse.ustaw_oplacona(ident,"2026-11-09")
        archived=self.home/"backup.zip"
        utworz_kopie(self.rejestr,archived)
        restored=przygotuj_przywracanie(archived,self.rejestr.katalog)
        try:
            connection=sqlite3.connect(restored.katalog_danych/"swistak.sqlite3")
            try:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM profile_rachunkow").fetchone()[0],1)
                self.assertGreater(connection.execute(
                    "SELECT COUNT(*) FROM dziennik_zdarzen").fetchone()[0],0)
                self.assertEqual(connection.execute(
                    "SELECT data_oplacenia FROM rachunki WHERE id=?",(ident,)
                ).fetchone()[0],"2026-11-09")
            finally:
                connection.close()
        finally:
            restored.sprzataj()


class TestMigracjaEtap3(unittest.TestCase):
    def test_stara_baza_002_jest_migrowana_z_zachowaniem_danych(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            data=root/"dane"
            dbfile=data/"swistak.sqlite3"
            conn=polacz(dbfile)
            try:
                base=root/"archiwalne-migracje"
                base.mkdir()
                schema=Path(__file__).resolve().parents[1]/"baza"/"schemat"
                for name in ("001_start.sql","002_numer_konta.sql"):
                    (base/name).write_bytes((schema/name).read_bytes())
                zastosuj_migracje(conn,base)
                conn.execute(
                    "INSERT INTO dokumenty(nazwa_zrodlowa,sha256,sciezka_wzgledna,rozmiar_bajtow) "
                    "VALUES ('fikcyjna.pdf',?,'dokumenty/aa/demo.pdf',20)",("a"*64,)
                )
                conn.execute(
                    "INSERT INTO rachunki(dokument_id,dostawca,kwota_grosze,status) "
                    "VALUES (1,'Firma DEMO',12345,'oplacony')"
                )
            finally:
                conn.close()
            upgraded=RejestrRachunkow(data)
            try:
                row=upgraded.db.execute("SELECT * FROM rachunki WHERE id=1").fetchone()
                self.assertEqual(row["kwota_grosze"],12345)
                self.assertEqual(row["status"],"oplacony")
                self.assertIsNone(row["data_oplacenia"])
                self.assertEqual(row["wersja_rekordu"],1)
                self.assertEqual(upgraded.db.execute(
                    "SELECT COUNT(*) FROM migracje").fetchone()[0],5)
                self.assertEqual(len(list((data/"kopie_migracji").glob("*.sqlite3"))),1)
                self.assertEqual(upgraded.db.execute("PRAGMA foreign_key_check").fetchall(),[])
            finally:
                upgraded.zamknij()


if __name__=="__main__":
    unittest.main()
