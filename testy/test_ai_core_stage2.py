# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 2 AI Core — syntetyczne SQLite, Tool Gateway i symulowana Ollama."""
from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ai_core import AgentOrchestrator, ModelBinding, ModelRouter, OllamaProvider, ToolGateway
from ai_core.contracts import sanitize_result
from ai_core.errors import InvalidResponse
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


def make_task(gateway, *, task_id="test-gateway", allowed=("invoice.search", "payment.inspect")):
    return {
        "contract_version": "1.0", "task_id": task_id, "role": "main",
        "instruction": "Sprawdź zaległości według SQLite",
        "context": {"reference_date": "2026-11-13"},
        "allowed_tools": list(allowed), "response_schema": "AnalysisResult",
        "data_revision": gateway.revision(), "locale": "pl",
        "timezone": "Europe/Warsaw",
        "limits": {"max_steps": 5, "timeout_ms": 15000, "max_records": 100}
    }


def tool_call(task, name, args, call_id="c1"):
    return {"contract_version": "1.0", "task_id": task["task_id"],
            "call_id": call_id, "tool_name": name, "tool_version": "1.0",
            "arguments": args, "data_revision": task["data_revision"]}


def finding_result(task, model, evidence, *, code="INVOICE_OVERDUE"):
    return {
        "contract_version": "1.0", "task_id": task["task_id"],
        "model_id": model, "status": "completed",
        "findings": [{
            "finding_id": "f1", "code": code, "severity": "warning",
            "summary": "Fikcyjna faktura wymaga kontroli.",
            "verification": "verified", "evidence": evidence,
        }],
        "proposed_actions": [{
            "action_id": "a1", "kind": "open_invoice", "target_type": "invoice",
            "target_id": "1", "parameters": {},
            "expected_data_revision": task["data_revision"],
            "requires_confirmation": True, "reason": "Wyświetl szczegóły",
        }],
        "uncertainties": [], "data_revision": task["data_revision"],
        "diagnostics": {"steps": 1},
    }


class TestToolGateway(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "dane"
        self.register = RejestrRachunkow(self.root)
        category = int(self.register.kategorie()[0]["id"])
        for nr, due, paid, amt in (
            (1, "2026-11-05", "do_zaplaty", "180,00"),
            (2, "2026-11-13", "do_zaplaty", "25,00"),
            (3, "2026-11-20", "oplacony", "100,00"),
        ):
            pdf = Path(self.temp.name) / f"synthetic-{nr}.pdf"
            pdf.write_bytes(f"%PDF-1.4\nTEST-NIEPRYWATNY-{nr}\n%%EOF\n".encode("utf-8"))
            document_id, _ = self.register.importuj_pdf(pdf)
            self.register.zapisz_rachunek(DaneRachunku(
                dokument_id=document_id, dostawca=f"Fikcyjny-{nr}",
                numer=f"TEST/{nr}", kwota=amt,
                kategoria_id=category, termin_platnosci=due,
                okres_od="2026-10-01", okres_do="2026-10-31",
                data_wystawienia="2026-11-02", status=paid,
            ))
        self.gateway = ToolGateway(self.root / "swistak.sqlite3")
        self.task = make_task(self.gateway)

    def tearDown(self):
        self.register.zamknij()
        self.temp.cleanup()

    def execute(self, session, name, args, call_id="x1"):
        return session.execute(tool_call(self.task, name, args, call_id))

    def test_faktury_i_filtry_i_pozycje(self):
        self.task["allowed_tools"] = ["invoice.search", "invoice.details", "invoice.lines"]
        with self.gateway.session(self.task) as session:
            listing = self.execute(session, "invoice.search", {"limit": 2}, "search")
            self.assertEqual(listing["status"], "ok")
            self.assertEqual(len(listing["data"]["invoices"]), 2)
            selected = self.execute(session, "invoice.details", {"invoice_id": 1}, "details")
            self.assertEqual(selected["data"]["kwota_grosze"], 18000)
            rows = self.execute(session, "invoice.lines", {"invoice_id": 1}, "lines")
            self.assertEqual(sum(r["kwota_grosze"] for r in rows["data"]["lines"]), 18000)
            filtering = self.execute(session, "invoice.search", {"supplier": "fikcyjny-1"}, "filter")
            self.assertEqual(len(filtering["data"]["invoices"]), 1)
        self.assertEqual(self.gateway.revision(), self.task["data_revision"])

    def test_daty_graniczne_i_weryfikacja_dowodu(self):
        with self.gateway.session(self.task) as session:
            late = self.execute(session, "payment.inspect", {"invoice_id": 1, "reference_date": "2026-11-13"}, "late")
            today = self.execute(session, "payment.inspect", {"invoice_id": 2, "reference_date": "2026-11-13"}, "today")
            self.assertEqual(late["data"]["days_overdue"], 8)
            self.assertFalse(today["data"]["overdue"])
            result = finding_result(self.task, "model-test", late["evidence"])
            sanitized = sanitize_result(result, self.task, "model-test", verifier=session.trusted_evidence)
            self.assertEqual(sanitized["findings"][0]["verification"], "verified")
            self.assertEqual(len(sanitized["findings"][0]["evidence"]), 1)
            forged = finding_result(self.task, "model-test", today["evidence"])
            self.assertEqual(
                sanitize_result(forged, self.task, "model-test", verifier=session.trusted_evidence)
                ["findings"][0]["verification"], "unverified"
            )
            unrelated = finding_result(self.task, "model-test", late["evidence"], code="SOME_OTHER_CLAIM")
            self.assertEqual(
                sanitize_result(unrelated, self.task, "model-test", verifier=session.trusted_evidence)
                ["findings"][0]["evidence"], []
            )

    def test_odrzuca_sql_i_niewlasciwe_parametry(self):
        with self.gateway.session(self.task) as session:
            no = self.execute(session, "invoice.details", {"invoice_id": 1}, "not-allowed")
            self.assertEqual(no["error"]["code"], "permission_denied")
            injection = self.execute(session, "invoice.search", {"supplier": "test", "sql": "DROP TABLE rachunki"}, "extra")
            self.assertEqual(injection["error"]["code"], "invalid_arguments")
            invalid_date = self.execute(session, "payment.inspect", {"invoice_id": 1, "reference_date": "2026-02-30"}, "date")
            self.assertEqual(invalid_date["error"]["code"], "invalid_arguments")
            with self.assertRaises(InvalidResponse):
                self.execute(session, "invoice.search", {}, "extra")
            bad = self.execute(session, "DROP TABLE rachunki", {}, "drop")
            self.assertEqual(bad["error"]["code"], "permission_denied")
        self.assertEqual(self.register.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 3)

    def test_niedostepne_przyszle_moduly_nie_zwracaja_fikcyjnych_danych(self):
        self.task["allowed_tools"] = ["plan.expected", "cycle.evaluate", "finance.aggregate"]
        with self.gateway.session(self.task) as session:
            plan = self.execute(session, "plan.expected", {"cycle": "2026-10"}, "plan")
            self.assertEqual(plan["status"], "error")
            self.assertEqual(plan["error"]["code"], "provider_unavailable")
            self.assertEqual(plan["data"], {})
            cycle = self.execute(session, "cycle.evaluate", {"cycle": "2026-10"}, "cycle")
            self.assertEqual(cycle["status"], "error")
            payments = self.execute(session, "finance.aggregate", {
                "basis": "paid_date", "period_from": "2026-11-01",
                "period_to": "2026-11-30"
            }, "payment")
            self.assertEqual(payments["error"]["code"], "provider_unavailable")

    def test_aggregate_grosze_i_pdf_sha(self):
        self.task["allowed_tools"] = ["finance.aggregate", "document.verify", "date.evaluate"]
        with self.gateway.session(self.task) as session:
            total = self.execute(session, "finance.aggregate", {
                "basis": "billing_end", "period_from": "2026-10-01",
                "period_to": "2026-10-31", "group_by": "month"
            }, "sum")
            self.assertEqual(total["data"]["total_grosze"], 30500)
            dt = self.execute(session, "date.evaluate", {
                "value": "2026-11-05", "reference_date": "2026-11-13"
            }, "date")
            self.assertEqual(dt["data"]["difference_days"], -8)
            doc = self.execute(session, "document.verify", {"document_id": 1}, "pdf")
            self.assertTrue(doc["data"]["valid_sha256"])
            self.assertEqual(len(doc["evidence"]), 1)

    def test_stare_zadanie_odrzucane(self):
        self.task["data_revision"] = "db:stara-baza"
        with self.assertRaises(InvalidResponse):
            with self.gateway.session(self.task):
                pass

    def test_sesja_nie_przyznaje_sobie_dostepu_do_zapisu(self):
        self.task["allowed_tools"] = ["invoice.search"]
        with self.gateway.session(self.task) as session:
            with self.assertRaises(sqlite3.OperationalError):
                session.db.execute("DELETE FROM rachunki")
            self.assertEqual(self.execute(session, "invoice.search", {}, "read")["status"], "ok")
        self.assertEqual(self.register.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0], 3)


class MockOllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        messages = payload["messages"]
        task = json.loads(messages[1]["content"])
        has_tool = any(m["role"] == "tool" for m in messages)
        if not has_tool:
            answer = {"message": {"content": "", "tool_calls": [
                {"function": {"name": self.server.request_tool,
                              "arguments": {"invoice_id": 1, "reference_date": "2026-11-13"}}}
            ]}}
        else:
            tool_result = json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))
            ev = tool_result["evidence"]
            answer = {"message": {"content": json.dumps(
                finding_result(task, payload["model"], ev), ensure_ascii=False
            )}}
        body = json.dumps(answer, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


class TestNativeOllamaTools(TestToolGateway):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockOllamaHandler)
        cls.server.request_tool = "payment.inspect"
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    def _agent(self, task_id, allowed):
        task = make_task(self.gateway, task_id=task_id, allowed=allowed)
        provider = OllamaProvider(f"http://127.0.0.1:{self.server.server_port}", timeout=5)
        router = ModelRouter({"ollama": provider}, ModelBinding("ollama", "fake-model"))
        return AgentOrchestrator(router, gateway=self.gateway), task

    def test_model_wywoluje_narzedzie_i_otrzymuje_dowod(self):
        self.server.request_tool = "payment.inspect"
        agent, task = self._agent("model-tool-1", ["payment.inspect"])
        events = []
        try:
            answer = agent.submit(task, events.append).result(timeout=6)
            self.assertEqual(answer["findings"][0]["verification"], "verified")
            self.assertEqual(answer["findings"][0]["evidence"][0]["source_id"], "1")
            self.assertEqual([e.kind for e in events], ["tool_call", "tool_result"])
            self.assertTrue(answer["proposed_actions"][0]["requires_confirmation"])
        finally:
            agent.shutdown()

    def test_zabronione_narzedzie_nie_zostaje_wykonane(self):
        self.server.request_tool = "payment.inspect"
        agent, task = self._agent("model-tool-denied", ["invoice.search"])
        try:
            result = agent.submit(task).result(timeout=6)
            self.assertEqual(result["findings"][0]["verification"], "unverified")
            self.assertEqual(result["findings"][0]["evidence"], [])
        finally:
            agent.shutdown()

    def test_brak_gateway_wciaz_blokuje_narzedzia(self):
        provider = OllamaProvider(f"http://127.0.0.1:{self.server.server_port}", timeout=5)
        router = ModelRouter({"ollama": provider}, ModelBinding("ollama", "fake-model"))
        from ai_core.errors import ToolGatewayPending
        with AgentOrchestrator(router) as agent:
            with self.assertRaises(ToolGatewayPending):
                agent.submit(make_task(self.gateway, task_id="without-gateway",
                                       allowed=["invoice.search"]))


if __name__ == "__main__":
    unittest.main()
