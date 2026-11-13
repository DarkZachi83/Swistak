# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 1 AI Core: Ollama symulowana na 127.0.0.1, bez modeli i prywatnych danych."""
from __future__ import annotations

import copy
import json
import threading
import unittest
from concurrent.futures import CancelledError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ai_core import (
    AgentOrchestrator, InvalidResponse, ModelBinding, ModelRouter,
    ModelUnavailable, OllamaProvider, TaskCancelled, ToolGatewayPending,
)
from ai_core.contracts import analysis_schema, validate
from ai_core.errors import AICoreError

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = json.loads(
    (ROOT / "testy" / "dane_syntetyczne" / "ai_core_v1.json").read_text(encoding="utf-8")
)


def task(*, task_id="demo-task-1", role="main", allowed_tools=()):
    request = copy.deepcopy(SYNTHETIC["task_request"])
    request["task_id"] = task_id
    request["role"] = role
    request["allowed_tools"] = list(allowed_tools)
    return request


def answer(request, model_id):
    result = copy.deepcopy(SYNTHETIC["analysis_result"])
    result["task_id"] = request["task_id"]
    result["model_id"] = model_id
    result["data_revision"] = request["data_revision"]
    result["findings"][0]["verification"] = "verified"  # celowy test granicy zaufania
    result["proposed_actions"][0]["expected_data_revision"] = request["data_revision"]
    return result


class LocalOllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "model-a"}, {"name": "model-b"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        self.server.calls.append((self.path, payload))
        if self.path == "/api/show":
            self._send({"capabilities": ["completion", "tools"], "model_info": {
                "mock.context_length": 8192
            }})
            return
        if self.path != "/api/chat":
            self.send_error(404)
            return
        request = json.loads(payload["messages"][-1]["content"])
        response = answer(request, payload["model"])
        if self.server.mode == "wrong_revision":
            response["data_revision"] = "db:old"
        text = json.dumps(response, ensure_ascii=False)
        if self.server.mode == "invalid_json":
            text = "{błędny json"
        if self.server.mode == "tool_call":
            reply = {"content": text, "tool_calls": [{"function": {"name": "invoice.search"}}]}
        else:
            reply = {"content": text}
        if payload["stream"] is False:
            self._send({"message": reply, "done": True})
            return
        chunks = [text[:len(text)//2], text[len(text)//2:]]
        frames = [{"message": {"content": part}, "done": False} for part in chunks]
        frames.append({"message": {"content": ""}, "done": True})
        if self.server.mode == "tool_call":
            frames[0]["message"]["tool_calls"] = reply["tool_calls"]
        body = "".join(json.dumps(frame, ensure_ascii=False) + "\n" for frame in frames).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestOllamaAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LocalOllamaHandler)
        cls.server.calls = []
        cls.server.mode = "ok"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.provider = OllamaProvider(f"http://127.0.0.1:{cls.server.server_port}", timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.server.mode = "ok"
        self.server.calls.clear()

    def test_localny_adres_i_brak_przekierowania_na_chmure(self):
        for address in ["https://127.0.0.1:11434", "http://example.com:11434",
                        "http://127.0.0.1.evil.com:11434",
                        "http://127.0.0.1:11434/somepath",
                        "http://user:pass@localhost:11434"]:
            with self.subTest(address=address), self.assertRaises(ValueError):
                OllamaProvider(address)
        self.assertTrue(self.provider.is_local)

    def test_modele_healthcheck_i_capabilities(self):
        self.assertEqual(self.provider.list_models(), ["model-a", "model-b"])
        self.assertTrue(self.provider.health_check("model-a"))
        self.assertFalse(self.provider.health_check("model-c"))
        caps = self.provider.get_capabilities("model-a")
        self.assertEqual(caps["declared"]["context_tokens"], 8192)
        self.assertTrue(caps["declared"]["native_tools"])
        self.assertFalse(caps["verified"])

    def test_generacja_i_izolacja_danych(self):
        request = task()
        result = self.provider.generate(request, "model-a")
        validate("AnalysisResult", result)
        self.assertEqual(result["model_id"], "model-a")
        self.assertEqual(result["data_revision"], request["data_revision"])
        self.assertEqual(result["findings"][0]["verification"], "unverified")
        self.assertEqual(result["findings"][0]["evidence"], [])
        self.assertTrue(result["proposed_actions"][0]["requires_confirmation"])
        path, payload = self.server.calls[-1]
        self.assertEqual(path, "/api/chat")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], "model-a")
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["format"]["type"], "object")
        self.assertEqual(payload["format"]["properties"], analysis_schema()["properties"])

    def test_stream_zakonczony_spojnym_wynikiem(self):
        events = list(self.provider.stream(task(task_id="stream-1"), "model-b"))
        self.assertGreater(len(events), 2)
        self.assertEqual(events[0].kind, "delta")
        self.assertEqual(events[-1].kind, "completed")
        self.assertEqual(events[-1].result["model_id"], "model-b")
        self.assertEqual(events[-1].result["findings"][0]["verification"], "unverified")
        self.assertTrue(self.server.calls[-1][1]["stream"])

    def test_bledny_json_i_nieaktualna_rewizja(self):
        self.server.mode = "invalid_json"
        with self.assertRaises(InvalidResponse):
            self.provider.generate(task(task_id="bad-json"), "model-a")
        self.server.mode = "wrong_revision"
        with self.assertRaises(InvalidResponse):
            self.provider.generate(task(task_id="wrong-rev"), "model-a")

    def test_model_nie_moze_wywolac_narzedzia(self):
        self.server.mode = "tool_call"
        with self.assertRaises(ToolGatewayPending):
            self.provider.generate(task(task_id="tools-1"), "model-a")
        with self.assertRaises(ToolGatewayPending):
            list(self.provider.stream(task(task_id="tools-2"), "model-a"))
        with self.assertRaises(ToolGatewayPending):
            self.provider.generate(task(task_id="tools-3", allowed_tools=["invoice.search"]), "model-a")

    def test_wymagana_poprawna_koperta(self):
        with self.assertRaises(InvalidResponse):
            self.provider.generate({"task_id": "niekompletne"}, "model-a")


class StubProvider:
    is_local = True

    def __init__(self, *, unavailable=False, block=False):
        self.unavailable = unavailable
        self.block = block
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = []
        self.models = []

    def health_check(self, model_id):
        return not self.unavailable

    def list_models(self):
        return ["stub"]

    def get_capabilities(self, model_id):
        return {"verified": False}

    def generate(self, request, model_id):
        self.models.append(model_id)
        self.started.set()
        if self.unavailable:
            raise ModelUnavailable("Fikcyjny model niedostępny")
        if self.block:
            if not self.release.wait(3):
                raise AICoreError("Test przekroczył czas")
        return answer(request, model_id)

    def stream(self, request, model_id):
        yield from ()

    def cancel(self, task_id):
        self.cancelled.append(task_id)
        self.release.set()


class TestRoutingAndOrchestration(unittest.TestCase):
    def test_dwa_modele_ten_sam_kontrakt(self):
        outputs = []
        for model in ("driver-a", "driver-b"):
            stub = StubProvider()
            router = ModelRouter({"local": stub}, ModelBinding("local", model))
            agent = AgentOrchestrator(router)
            try:
                result = agent.submit(task(task_id="same-contract")).result(timeout=3)
                outputs.append(result)
            finally:
                agent.shutdown()
        self.assertEqual([x["model_id"] for x in outputs], ["driver-a", "driver-b"])
        self.assertEqual(outputs[0]["task_id"], outputs[1]["task_id"])

    def test_specjalista_i_zapasowy_glowny(self):
        main = StubProvider()
        specialist = StubProvider(unavailable=True)
        router = ModelRouter(
            {"primary": main, "specialist": specialist},
            ModelBinding("primary", "main-model"),
            {"extractor": ModelBinding("specialist", "extract-model", frozenset({"extractor"}))}
        )
        agent = AgentOrchestrator(router)
        try:
            result = agent.submit(task(task_id="fall-back", role="extractor")).result(timeout=3)
            self.assertEqual(result["model_id"], "main-model")
            self.assertEqual(specialist.models, ["extract-model"])
            self.assertEqual(main.models, ["main-model"])
        finally:
            agent.shutdown()

    def test_blokada_zewnetrznego_dostawcy_i_tools(self):
        provider = StubProvider()
        provider.is_local = False
        with self.assertRaises(ValueError):
            ModelRouter({"cloud": provider}, ModelBinding("cloud", "model"))
        provider.is_local = True
        router = ModelRouter({"local": provider}, ModelBinding("local", "model"))
        agent = AgentOrchestrator(router)
        try:
            with self.assertRaises(ToolGatewayPending):
                agent.submit(task(task_id="tools-blocked", allowed_tools=["invoice.search"]))
            self.assertFalse(provider.models)
        finally:
            agent.shutdown()

    def test_anulowanie_i_odrzucenie_spoznionego_wyniku(self):
        provider = StubProvider(block=True)
        router = ModelRouter({"local": provider}, ModelBinding("local", "main-model"))
        agent = AgentOrchestrator(router)
        try:
            future = agent.submit(task(task_id="cancel-me"))
            self.assertTrue(provider.started.wait(2))
            self.assertTrue(agent.cancel("cancel-me"))
            with self.assertRaises((TaskCancelled, CancelledError)):
                future.result(timeout=3)
            self.assertIn("cancel-me", provider.cancelled)
            self.assertFalse(agent.cancel("cancel-me"))
        finally:
            provider.release.set()
            agent.shutdown()


if __name__ == "__main__":
    unittest.main()
