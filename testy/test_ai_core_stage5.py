# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 5: hybryda/offline, priorytety, dowody, log i Panel Agenta."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

import ustawienia
from testy.pomoc_qt import zamknij_widget
from ai_core.errors import InvalidResponse, ModelUnavailable, TaskCancelled
from ai_core.gateway import ToolGateway
from ai_core.hybrid import AgentLog, HybridAgent, MonitorReport
from ai_core.hybrid_queue import MonitorJob, MonitorQueue
from ai_core.ollama import OllamaProvider
from gui.okno_glowne import OknoGlowne
from gui.panel_agenta import PanelAgenta, report_text
from uslugi.finanse import Finanse
from uslugi.plan_rachunkow import PlanRachunkow
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


class UnavailableProvider:
    is_local = True

    def health_check(self, model_id):
        return False


class DeterministicFakeProvider:
    is_local = True

    def __init__(self):
        self.calls = []
        self.cancelled = []

    def health_check(self, model_id):
        return True

    def run_tools(self, task, model_id, session, progress=None):
        self.calls.append((task["context"], model_id))
        invoice_id = task["context"].get("scope_invoice_id") or 1
        request = {
            "contract_version": "1.0", "task_id": task["task_id"],
            "call_id": "test-payment-check", "tool_name": "payment.inspect",
            "tool_version": "1.0", "data_revision": task["data_revision"],
            "arguments": {
                "invoice_id": invoice_id,
                "reference_date": task["context"]["reference_date"],
            },
        }
        evidence = session.execute(request)["evidence"]
        return {
            "contract_version": "1.0",
            "task_id": task["task_id"], "model_id": model_id,
            "status": "completed",
            "findings": [{
                "finding_id": "test-finding", "code": "INVOICE_OVERDUE",
                "severity": "warning",
                "summary": "Sprawdź fikcyjny przeterminowany rachunek",
                "verification": "verified", "evidence": evidence,
            }],
            "proposed_actions": [{
                "action_id": "proposal-1", "kind": "mark_paid",
                "target_type": "invoice", "target_id": str(invoice_id),
                "parameters": {"paid_date": "2026-11-13"},
                "expected_data_revision": task["data_revision"],
                "requires_confirmation": True,
                "reason": "Wyłącznie propozycja, bez zapisu",
            }],
            "uncertainties": [],
            "data_revision": task["data_revision"], "diagnostics": {},
        }

    def cancel(self, task_id):
        self.cancelled.append(task_id)


class TestHybridAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.register = RejestrRachunkow(root / "dane")
        category = int(self.register.kategorie()[0]["id"])
        pdf = root / "TYLKO_FIKCYJNY.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%CI synthetic\n%%EOF")
        document, _ = self.register.importuj_pdf(pdf)
        self.invoice_id = self.register.zapisz_rachunek(DaneRachunku(
            dokument_id=document, dostawca="DEMO fikcyjna",
            numer="TEST/2026/10", kwota="180,00", kategoria_id=category,
            okres_od="2026-10-01", okres_do="2026-10-31",
            data_wystawienia="2026-11-01",
            termin_platnosci="2026-11-05",
            status="do_zaplaty",
        ))
        self.path = self.register.katalog / "swistak.sqlite3"

    def tearDown(self):
        self.register.zamknij()
        self.tmp.cleanup()

    def _agent(self, provider):
        return HybridAgent(
            self.path, "model-demo", reference_date="2026-11-13",
            provider_factory=lambda: provider,
        )

    def test_startup_bez_ollamy_wskazuje_prawdziwe_zaleglosci(self):
        agent = self._agent(UnavailableProvider())
        report = agent.run("startup")
        self.assertEqual(report.model_status, "local_only")
        self.assertEqual(report.summary["invoices"], 1)
        self.assertEqual(report.summary["unpaid_grosze"], 18000)
        self.assertEqual(report.summary["overdue"], 1)
        self.assertEqual(report.summary["due_soon"], 0)
        self.assertFalse(report.findings)
        self.assertEqual(self.register.rachunek(1)["status"], "do_zaplaty")

    def test_wstrzymanie_profilu_zachowuje_zapisane_oczekiwanie_w_agencie_i_rozliczeniu(self):
        plan = PlanRachunkow(self.register.db)
        finance = Finanse(self.register.db)
        profil = plan.utworz_profil("DEMO cykliczny", cykl_od="2026-10")
        finance.ustaw_oplacona(self.invoice_id, "2026-11-04")
        [oczekiwanie] = plan.generuj_oczekiwania("2026-10")
        plan.ustaw_aktywnosc(profil, False, powod="Syntetyczne wstrzymanie")
        self.assertEqual(plan.generuj_oczekiwania("2026-11"), [])
        ocena = finance.ocena_cyklu("2026-10", dzisiaj="2026-11-13")
        self.assertEqual((ocena["missing_expected"], ocena["unresolved_expected"]), (1, 1))
        agent = self._agent(UnavailableProvider())
        self.assertEqual(agent.run("startup").summary["missing_expected"], 1)
        with self.assertRaisesRegex(ValueError, "oczekiwane dokumenty"):
            finance.potwierdz_kompletnosc("2026-10", dzisiaj="2026-11-13")

        gateway = ToolGateway(self.path)
        task = agent._task("manual", None, gateway.revision(), tools=True)
        with gateway.session(task) as session:
            expected = session.execute({
                "contract_version": "1.0", "task_id": task["task_id"],
                "call_id": "expected", "tool_name": "plan.expected", "tool_version": "1.0",
                "arguments": {"cycle": "2026-10"}, "data_revision": task["data_revision"],
            })
        self.assertEqual(expected["data"]["expected"][0]["id"], oczekiwanie)
        plan.powiaz(oczekiwanie, self.invoice_id)
        self.assertEqual(agent.run("startup").summary["missing_expected"], 0)
        finance.potwierdz_kompletnosc("2026-10", dzisiaj="2026-11-13")
        self.assertTrue(finance.ocena_cyklu("2026-10", dzisiaj="2026-11-13")["closed"])

    def test_start_sprawdza_ollame_nawet_przy_pustej_bazie(self):
        self.register.db.execute("DELETE FROM rachunki")
        provider = OllamaProvider()
        with patch.object(provider, "_request", return_value={"models": [{"name": "model-demo"}]}) as http:
            report = self._agent(provider).run("startup")
        self.assertEqual(report.model_status, "model_idle")
        self.assertEqual(report.model_id, "model-demo")
        http.assert_called_once_with("/api/tags", timeout=2.5)

    def test_start_bez_alertow_nie_laduje_modelu_z_faktura(self):
        self.register.db.execute(
            "UPDATE rachunki SET status='oplacony',data_oplacenia='2026-11-03' WHERE id=?",
            (self.invoice_id,),
        )
        provider = OllamaProvider()
        with patch.object(provider, "_request", return_value={"models": [{"name": "model-demo"}]}) as http:
            report = self._agent(provider).run("startup")
        self.assertEqual(report.model_status, "model_idle")
        self.assertEqual(report.summary["invoices"], 1)
        http.assert_called_once_with("/api/tags", timeout=2.5)

    def test_brak_modelu_i_brak_odpowiedzi_ollamy_to_rozne_przyczyny(self):
        provider = OllamaProvider()
        with patch.object(provider, "list_models", return_value=["inny-model"]):
            report = self._agent(provider).run("startup")
        self.assertEqual(report.model_status, "local_only")
        self.assertEqual(report.model_reason, "model_missing")
        self.assertIn("model-demo", report_text(report))
        with patch.object(provider, "list_models", side_effect=ModelUnavailable("offline")):
            report = self._agent(provider).run("startup")
        self.assertEqual(report.model_reason, "ollama_unavailable")

    def test_model_bez_narzedzi_zostaje_dostepny_bez_wywolania_chat(self):
        provider = OllamaProvider()
        with patch.object(provider, "_request", side_effect=[
            {"models": [{"name": "model-demo"}]}, {"capabilities": ["completion", "vision"]},
        ]) as http:
            report = self._agent(provider).run("manual")
        self.assertEqual(report.model_status, "model_no_tools")
        self.assertEqual([call.args[0] for call in http.call_args_list], ["/api/tags", "/api/show"])

    def test_blad_analizy_zachowuje_model_i_kontrole_lokalna(self):
        provider = OllamaProvider()
        with (
            patch.object(provider, "_request", side_effect=[
                {"models": [{"name": "model-demo"}]}, {"capabilities": ["completion", "tools"]},
            ]),
            patch.object(provider, "run_tools", side_effect=InvalidResponse("Dane dostawcy DEMO")),
        ):
            report = self._agent(provider).run("manual")
        self.assertEqual(report.model_status, "model_error")
        self.assertEqual(report.model_reason, "invalid_response")
        self.assertEqual(report.model_id, "model-demo")
        self.assertEqual(report.summary["overdue"], 1)
        self.assertNotIn("Dane dostawcy DEMO", report_text(report))

    def test_po_zapisie_tylko_wskazany_rachunek(self):
        agent = self._agent(UnavailableProvider())
        report = agent.run("change", self.invoice_id)
        self.assertEqual(report.invoice_id, self.invoice_id)
        self.assertEqual(report.summary["invoices"], 1)
        self.assertEqual(report.summary["missing_expected"], 0)
        with self.assertRaises(ValueError):
            agent.run("change")
        with self.assertRaises(ValueError):
            agent.run("manual", self.invoice_id)

    def test_model_uzywa_gateway_a_propozycja_nie_ksieguje(self):
        provider = DeterministicFakeProvider()
        agent = self._agent(provider)
        report = agent.run("manual")
        self.assertEqual(report.model_status, "model_ready")
        self.assertEqual(report.findings[0]["verification"], "verified")
        self.assertTrue(report.proposals[0]["requires_confirmation"])
        self.assertEqual(provider.calls[0][1], "model-demo")
        self.assertEqual(self.register.rachunek(1)["status"], "do_zaplaty")
        self.assertEqual(self.register.db.execute(
            "SELECT COUNT(*) FROM dziennik_zdarzen WHERE operacja='oplacenie'"
        ).fetchone()[0], 0)

    def test_scope_tool_gateway_nie_wpuszcza_innej_faktury(self):
        task = self._agent(UnavailableProvider())._task(
            "change", self.invoice_id, ToolGateway(self.path).revision(), tools=True
        )
        with ToolGateway(self.path).session(task) as session:
            result = session.execute({
                "contract_version": "1.0", "task_id": task["task_id"],
                "call_id": "scope", "tool_name": "payment.inspect",
                "tool_version": "1.0",
                "data_revision": task["data_revision"],
                "arguments": {
                    "invoice_id": self.invoice_id + 1,
                    "reference_date": "2026-11-13",
                }
            })
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error"]["code"], "permission_denied")
            self.assertEqual(result["evidence"], [])

    def test_odczyt_gateway_nie_blokuje_zapisu_i_odrzuca_stare_wyniki(self):
        gateway = ToolGateway(self.path)
        agent = self._agent(UnavailableProvider())
        task = agent._task("manual", None, gateway.revision(), tools=True)
        with self.assertRaises(Exception) as captured:
            with gateway.session(task) as session:
                self.register.db.execute(
                    "UPDATE rachunki SET kwota_grosze=kwota_grosze+1 WHERE id=?",
                    (self.invoice_id,),
                )
                # Gdyby sesja przytrzymywała BEGIN, zapis powyżej
                # zgłosiłby database is locked (lub zwlekał do timeout).
                session.execute({
                    "contract_version":"1.0","task_id":task["task_id"],
                    "call_id":"stale","tool_name":"invoice.details",
                    "tool_version":"1.0","data_revision":task["data_revision"],
                    "arguments":{"invoice_id":self.invoice_id}
                })
        from ai_core.errors import InvalidResponse
        self.assertIsInstance(captured.exception, InvalidResponse)

    def test_anulowanie_przed_startem_nie_dotyka_bazy(self):
        agent = self._agent(UnavailableProvider())
        agent.cancel()
        with self.assertRaises(TaskCancelled):
            agent.run("startup")
        self.assertEqual(self.register.rachunek(1)["status"], "do_zaplaty")


class TestAgentQueueAndLog(unittest.TestCase):
    def test_priority_replacement_and_coalescing(self):
        q = MonitorQueue()
        self.assertTrue(q.add(MonitorJob("startup")))
        self.assertTrue(q.add(MonitorJob("change", 1)))
        self.assertFalse(q.add(MonitorJob("change", 1)))
        self.assertTrue(q.add(MonitorJob("change", 2)))
        self.assertTrue(q.add(MonitorJob("manual")))
        self.assertFalse(q.add(MonitorJob("manual")))
        self.assertEqual(q.take(), MonitorJob("manual"))
        self.assertEqual(q.take(), MonitorJob("change", 1))
        self.assertEqual(q.take(), MonitorJob("change", 2))
        self.assertIsNone(q.take())

    def test_log_nie_ma_tresci_rachunku_i_limit(self):
        log = AgentLog(limit=2)
        log.append("startup", "started")
        log.append("change", "queued", 123)
        log.append("manual", "ai_done")
        self.assertEqual(len(log.text().splitlines()), 2)
        self.assertIn("invoice_id=123", log.text())
        self.assertNotIn("kwota", log.text())
        with self.assertRaises(ValueError):
            log.append("manual", "RAW_PDF_DATA")


class TestAgentPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_readonly_panel_no_action_applying(self):
        panel = PanelAgenta()
        report = MonitorReport(
            mode="manual", invoice_id=None, reference_date="2026-11-13",
            data_revision="db:test",
            summary={
                "invoices": 1, "unpaid_grosze": 18000, "overdue": 1,
                "due_soon": 0, "paid_without_date": 0, "missing_expected": 0
            },
            model_status="local_only",
        )
        panel.update_content(report, "2026-11-13 [manual] started", False)
        self.assertEqual(panel.wyniki.isReadOnly(), True)
        self.assertEqual(panel.dziennik.isReadOnly(), True)
        self.assertIn("180,00", report_text(report))
        self.assertFalse(panel.cancel.isEnabled())
        self.assertTrue(panel.manual.isEnabled())
        zamknij_widget(panel)

    def test_gui_nie_dodaje_siodmego_etapu_i_ma_panel(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rejestr = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "prefs.json"):
                    ustawienia.save({"language":"pl","ollama_model":"demo"})
                    win = OknoGlowne(rejestr)
                    self.assertEqual(win.kreator.nawigacja.count(), 5)
                    self.assertEqual(win.kreator.analiza.zakladki_ai.count(), 2)
                    self.assertEqual(win.kreator.analiza.btn_panel_agenta.objectName(),
                                     "panelAgentaWAnalizie")
                    self.assertEqual(win.monitor.status_key, "agent.state.waiting")
                    win.kreator.analiza.btn_panel_agenta.click()
                    self.assertIs(win.moduly.currentWidget(), win.monitor.panel)
                    self.assertFalse(win.monitor.panel.isWindow())
                    self.assertIsNone(win.monitor.report)
                    win.kreator.analiza.ed_model.setText(" model-wpisany ")
                    self.assertEqual(win.kreator.model, " model-wpisany ")
                    with patch("gui.monitor_agenta.QThreadPool.globalInstance") as pool:
                        win.monitor.zlec("manual")
                        self.assertEqual(win.monitor._current_job,
                                         MonitorJob("manual"))
                        pool.return_value.start.assert_called_once()
                        self.assertEqual(pool.return_value.start.call_args.args[0].model,
                                         "model-wpisany")
                        win.monitor.anuluj()
                    zamknij_widget(win)
            finally:
                rejestr.zamknij()


if __name__ == "__main__":
    unittest.main()
