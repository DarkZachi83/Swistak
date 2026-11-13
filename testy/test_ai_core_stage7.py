# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 7: role lokalnych modeli, bez zapisu AI i bez prawdziwych faktur."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QComboBox, QDialog

import ustawienia
from ai_core.errors import TaskCancelled
from ai_core.hybrid import HybridAgent
from gui.analiza_worker import ZadanieAnalizy
from gui.okno_glowne import OknoGlowne
from gui.panel_agenta import report_text
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class FakeRoleProvider:
    is_local = True

    def __init__(self, unavailable=(), fail_roles=(), cancel_on=None):
        self.calls = []
        self.checked = []
        self.cancelled = []
        self.unavailable = set(unavailable)
        self.fail_roles = set(fail_roles)
        self.cancel_on = cancel_on
        self.agent = None

    def health_check(self, model_id):
        self.checked.append(model_id)
        return model_id not in self.unavailable

    def cancel(self, task_id):
        self.cancelled.append(task_id)

    def run_tools(self, task, model_id, session, progress=None):
        self.calls.append((task["role"], model_id, task))
        if task["role"] in self.fail_roles:
            raise RuntimeError("Syntetyczna awaria modelu")
        if task["role"] == self.cancel_on and self.agent:
            self.agent.cancel()
        # Każda rola wykonuje wyłącznie własne dozwolone narzędzia.
        proof = []
        if "payment.inspect" in task["allowed_tools"]:
            response = session.execute({
                "contract_version": "1.0", "task_id": task["task_id"],
                "call_id": "payment-" + task["task_id"],
                "tool_name": "payment.inspect", "tool_version": "1.0",
                "data_revision": task["data_revision"],
                "arguments": {
                    "invoice_id": task["context"].get("scope_invoice_id") or 1,
                    "reference_date": task["context"]["reference_date"],
                },
            })
            proof = response["evidence"]
        findings = [{
            "finding_id": "finding-"+task["role"],
            "code": "INVOICE_OVERDUE",
            "severity": "warning",
            "summary": "Fikcyjna kontrola: testowa faktura po terminie",
            "verification": "verified",
            # Cykl nie ma prawa używać payment.inspect; sfingowany
            # dowód musi zostać zdegradowany przez sanitize_result.
            "evidence": proof if task["role"] != "cycle_analyst"
                        else [{"source_type":"invoice","source_id":"1",
                               "tool_call_id":"forged-proof",
                               "data_revision":task["data_revision"]}],
        }]
        actions = ([{
            "action_id":"proposal-"+task["role"],"kind":"mark_paid",
            "target_type":"invoice","target_id":"1",
            "parameters":{"paid_date":"2026-11-13"},
            "expected_data_revision":task["data_revision"],
            "requires_confirmation":True,
            "reason":"Tylko wniosek do ręcznego rozpatrzenia",
        }] if task["role"] != "main" else [])
        return {
            "contract_version":"1.0",
            "task_id":task["task_id"],"model_id":model_id,
            "status":"completed", "findings":findings,
            "proposed_actions":actions, "uncertainties":[],
            "data_revision":task["data_revision"],"diagnostics":{},
        }


class TestRoleConfiguration(unittest.TestCase):
    def test_old_settings_remain_compatible_and_optional_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"prefs.json"
            path.write_text(json.dumps({"ollama_model":"gemma2:9b"}),encoding="utf-8")
            prefs=ustawienia.load(path)
            self.assertEqual(prefs["ollama_model"],"gemma2:9b")
            self.assertEqual(ustawienia.modele_specjalistyczne(prefs),{})
            self.assertEqual(
                [prefs["model_"+role] for role in ustawienia.SPECIALIST_ROLES],
                ["","","",""],
            )

    def test_four_roles_persist_without_touching_main_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"prefs.json"
            prefs=dict(ustawienia.DEFAULTS,
                       ollama_model="main-demo",
                       model_extractor="extract-demo",
                       model_verifier="verify-demo",
                       model_financial_analyst="finance-demo",
                       model_cycle_analyst="cycle-demo")
            ustawienia.save(prefs,path)
            loaded=ustawienia.load(path)
            self.assertEqual(loaded["ollama_model"],"main-demo")
            self.assertEqual(ustawienia.modele_specjalistyczne(loaded),{
                "extractor":"extract-demo",
                "verifier":"verify-demo",
                "financial_analyst":"finance-demo",
                "cycle_analyst":"cycle-demo",
            })
            for key in ustawienia.SPECIALIST_KEYS:
                broken=dict(prefs,**{key:"model\nunsafe"})
                with self.assertRaises(ValueError):
                    ustawienia.save(broken,path)


class TestHybridSpecialists(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.reg=RejestrRachunkow(self.root/"data")
        cat=int(self.reg.kategorie()[0]["id"])
        pdf=self.root/"SYNTHETIC_STAGE7.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%synthetic\n%%EOF")
        doc,_=self.reg.importuj_pdf(pdf)
        self.invoice_id=self.reg.zapisz_rachunek(DaneRachunku(
            dokument_id=doc,dostawca="TEST firma",numer="TEST/7",
            kwota="150,00",kategoria_id=cat,
            data_wystawienia="2026-11-01",termin_platnosci="2026-11-05",
            okres_od="2026-10-01",okres_do="2026-10-31",
            status="do_zaplaty",
        ))
        self.path=self.reg.katalog/"swistak.sqlite3"

    def tearDown(self):
        self.reg.zamknij()
        self.tmp.cleanup()

    def agent(self, provider, specialist_models=None):
        agent=HybridAgent(
            self.path,"main-demo",reference_date="2026-11-13",
            provider_factory=lambda: provider,
            specialist_models=specialist_models,
        )
        provider.agent=agent
        return agent

    def test_no_specialists_maintains_original_single_model_behavior(self):
        fake=FakeRoleProvider()
        report=self.agent(fake).run("manual")
        self.assertEqual([r for r,_,_ in fake.calls],["main"])
        self.assertEqual(report.specialists,())
        self.assertEqual(report.model_status,"model_ready")
        self.assertEqual(self.reg.rachunek(1)["status"],"do_zaplaty")

    def test_three_roles_run_sequentially_after_main_with_read_only_tools(self):
        fake=FakeRoleProvider()
        roles={"verifier":"verify-demo",
               "financial_analyst":"finance-demo",
               "cycle_analyst":"cycle-demo"}
        report=self.agent(fake,roles).run("manual")
        self.assertEqual([r for r,_,_ in fake.calls],
                         ["main","verifier","financial_analyst","cycle_analyst"])
        self.assertEqual([r["status"] for r in report.specialists],
                         ["ready","ready","ready"])
        self.assertEqual(report.findings[0]["verification"],"verified")
        self.assertEqual(report.specialists[2]["findings"][0]["verification"],
                         "unverified")
        self.assertFalse(report.specialists[2]["findings"][0]["evidence"])
        self.assertFalse(any("proposals" in e for e in report.specialists))
        self.assertEqual(self.reg.rachunek(1)["status"],"do_zaplaty")
        self.assertNotIn("mark_paid",report_text(report))

    def test_unavailable_or_failing_specialist_does_not_discard_main_result(self):
        fake=FakeRoleProvider(unavailable={"verify-demo"},
                              fail_roles={"financial_analyst"})
        result=self.agent(fake,{"verifier":"verify-demo",
                                "financial_analyst":"finance-demo"}).run("manual")
        self.assertEqual(result.model_status,"model_ready")
        self.assertEqual([x["status"] for x in result.specialists],
                         ["unavailable","error"])
        self.assertEqual([x[0] for x in fake.calls],["main","financial_analyst"])

    def test_change_scope_skips_cycle_and_preserves_invoice_boundaries(self):
        fake=FakeRoleProvider()
        report=self.agent(fake,{
            "financial_analyst":"fin-demo",
            "cycle_analyst":"cycle-demo",
        }).run("change",self.invoice_id)
        self.assertEqual([x[0] for x in fake.calls],["main","financial_analyst"])
        self.assertEqual(report.specialists[1]["status"],"scope")
        task=fake.calls[1][2]
        self.assertEqual(task["context"]["scope_invoice_id"],self.invoice_id)
        self.assertEqual(set(task["allowed_tools"]),
                         {"invoice.details","payment.inspect","date.evaluate"})

    def test_cancellation_during_specialist_discards_all_in_flight_results(self):
        fake=FakeRoleProvider(cancel_on="verifier")
        with self.assertRaises(TaskCancelled):
            self.agent(fake,{"verifier":"verify-demo"}).run("manual")
        self.assertEqual(self.reg.rachunek(1)["status"],"do_zaplaty")
        self.assertTrue(fake.cancelled)

    def test_unknown_role_rejected_and_extractor_only_for_document_worker(self):
        fake=FakeRoleProvider()
        with self.assertRaises(ValueError):
            self.agent(fake,{"hacker":"model"})
        report=self.agent(fake,{"extractor":"extract-demo"}).run("manual")
        self.assertFalse(report.specialists)


class TestStage7Qt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_document_worker_passes_optional_extractor(self):
        worker=ZadanieAnalizy(1,"Fikcyjna faktura",["Gaz"],"main-demo",
                             model_ekstrakcji="extract-demo")
        with patch("gui.analiza_worker.analizuj_przez_ai_core",
                   return_value=object()) as analyze:
            worker.run()
        self.assertEqual(analyze.call_args.kwargs["model_ekstrakcji"],
                         "extract-demo")

    def test_dialog_configures_specialists_from_ollama_and_persists_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            reg=RejestrRachunkow(root/"data")
            try:
                with patch.object(ustawienia,"path_settings",
                                  return_value=root/"settings.json"):
                    ustawienia.save(dict(ustawienia.DEFAULTS,language="pl"))
                    win=OknoGlowne(reg)
                    try:
                        with patch("gui.okno_glowne.QThreadPool.globalInstance") as pool:
                            def inspect():
                                dialog=next(x for x in QApplication.topLevelWidgets()
                                            if x.objectName()=="ustawieniaSwistaka"
                                            and x.parent() is win)
                                selectors={role:dialog.findChild(
                                    QComboBox,"specialistModel_"+role)
                                    for role in ustawienia.SPECIALIST_ROLES}
                                self.assertTrue(all(selectors.values()))
                                self.assertEqual(selectors["extractor"].currentData(),"")
                                task=pool.return_value.start.call_args.args[0]
                                task.sygnaly.gotowe.emit(
                                    ["gemma3:4b","verify-demo","fin-demo"],""
                                )
                                self.assertGreaterEqual(selectors["verifier"].count(),4)
                                selectors["extractor"].setCurrentIndex(
                                    selectors["extractor"].findData("gemma3:4b"))
                                selectors["verifier"].setCurrentIndex(
                                    selectors["verifier"].findData("verify-demo"))
                                selectors["financial_analyst"].setCurrentIndex(
                                    selectors["financial_analyst"].findData("fin-demo"))
                                return QDialog.DialogCode.Accepted
                            with patch("gui.okno_glowne.QDialog.exec",
                                       side_effect=inspect):
                                win._open_settings()
                        prefs=ustawienia.load()
                        self.assertEqual(prefs["model_verifier"],"verify-demo")
                        self.assertEqual(prefs["model_extractor"],"gemma3:4b")
                        self.assertEqual(prefs["model_financial_analyst"],"fin-demo")
                        self.assertEqual(prefs["model_cycle_analyst"],"")
                        self.assertEqual(win.ed_model.text(),"gemma3:4b")
                        with patch("gui.okno_glowne.QThreadPool.globalInstance"):
                            def inspect_reopen():
                                dialog=next(x for x in QApplication.topLevelWidgets()
                                            if x.objectName()=="ustawieniaSwistaka"
                                            and x.parent() is win)
                                self.assertEqual(dialog.findChild(
                                    QComboBox,"specialistModel_verifier"
                                ).currentData(),"verify-demo")
                                return QDialog.DialogCode.Rejected
                            with patch("gui.okno_glowne.QDialog.exec",
                                       side_effect=inspect_reopen):
                                win._open_settings()
                    finally:
                        win.close()
            finally:
                reg.zamknij()


if __name__=="__main__":
    unittest.main()
