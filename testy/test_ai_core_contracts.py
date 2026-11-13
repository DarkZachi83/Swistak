# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 0 AI Core: kontrakty v1 i syntetyczne przykłady, bez LLM i SQLite."""
from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "ai_core"
FIXTURE = ROOT / "testy" / "dane_syntetyczne" / "ai_core_v1.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestAICoreContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load(DOCS / "contracts_v1.schema.json")
        cls.tools = load(DOCS / "tools_v1.json")
        cls.examples = load(FIXTURE)

    def check_shape(self, data: object, definition: dict) -> None:
        """Testy strukturalne podzbioru reguł, NIE pełny walidator JSON Schema."""
        if "$ref" in definition:
            prefix = "#/$defs/"
            self.assertTrue(definition["$ref"].startswith(prefix))
            return self.check_shape(data, self.schema["$defs"][definition["$ref"][len(prefix):]])
        if "oneOf" in definition:
            if data is None:
                self.assertTrue(any(d.get("type") == "null" for d in definition["oneOf"]))
                return
            candidates = [d for d in definition["oneOf"] if d.get("type") != "null"]
            self.assertTrue(candidates)
            return self.check_shape(data, candidates[0])
        if "const" in definition:
            self.assertEqual(data, definition["const"])
        if "enum" in definition:
            self.assertIn(data, definition["enum"])
        kind = definition.get("type")
        if kind == "object":
            self.assertIsInstance(data, dict)
            props = definition.get("properties", {})
            self.assertTrue(set(definition.get("required", [])) <= data.keys())
            if definition.get("additionalProperties") is False:
                self.assertFalse(set(data) - set(props))
            for key, value in data.items():
                if key in props:
                    self.check_shape(value, props[key])
        elif kind == "array":
            self.assertIsInstance(data, list)
            for value in data:
                self.check_shape(value, definition["items"])
            if definition.get("uniqueItems"):
                self.assertEqual(len(data), len({json.dumps(x, sort_keys=True) for x in data}))
            if "minItems" in definition:
                self.assertGreaterEqual(len(data), definition["minItems"])
        elif kind == "integer":
            self.assertIs(type(data), int)
            if "minimum" in definition:
                self.assertGreaterEqual(data, definition["minimum"])
            if "maximum" in definition:
                self.assertLessEqual(data, definition["maximum"])
        elif kind == "boolean":
            self.assertIs(type(data), bool)
        elif kind == "string":
            self.assertIsInstance(data, str)
            if "minLength" in definition:
                self.assertGreaterEqual(len(data), definition["minLength"])
            if definition.get("format") == "date":
                self.assertEqual(date.fromisoformat(data).isoformat(), data)
        elif kind == "null":
            self.assertIsNone(data)

    def test_schema_i_wersje(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.tools["catalog_version"], "1.0")
        self.assertEqual(self.examples["fixture_version"], "1.0")
        for name in ("TaskRequest", "ToolCall", "ToolResult", "AnalysisResult", "ModelProfile"):
            self.assertIn(name, self.schema["$defs"])
            self.assertFalse(self.schema["$defs"][name]["additionalProperties"])

    def test_koperty_syntetyczne(self):
        cases = {
            "task_request": "TaskRequest", "tool_call": "ToolCall",
            "tool_result": "ToolResult", "analysis_result": "AnalysisResult",
            "model_profile": "ModelProfile",
        }
        for fixture_name, schema_name in cases.items():
            with self.subTest(koperta=schema_name):
                self.check_shape(self.examples[fixture_name], self.schema["$defs"][schema_name])
        request = self.examples["task_request"]
        call = self.examples["tool_call"]
        result = self.examples["tool_result"]
        analysis = self.examples["analysis_result"]
        self.assertEqual(call["task_id"], request["task_id"])
        self.assertEqual(result["call_id"], call["call_id"])
        self.assertEqual(analysis["task_id"], request["task_id"])
        self.assertEqual(result["data_revision"], analysis["data_revision"])
        self.assertEqual(request["data_revision"], analysis["data_revision"])
        self.assertIn(call["tool_name"], request["allowed_tools"])

    def test_katalog_tylko_odczyt_i_ograniczenia(self):
        entries = self.tools["tools"]
        self.assertEqual(len(entries), 12)
        names = [entry["name"] for entry in entries]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(self.tools["read_only"])
        for entry in entries:
            self.assertEqual(entry["version"], "1.0")
            self.assertEqual(entry["effect"], "read")
            self.assertLessEqual(entry["max_records"], 200)
            spec = entry["input_schema"]
            self.assertEqual(spec["type"], "object")
            self.assertFalse(spec["additionalProperties"])
            self.assertTrue(set(spec["required"]) <= spec["properties"].keys())
        self.assertEqual(self.examples["tool_call"]["tool_name"], "payment.inspect")
        self.assertIn(self.examples["tool_call"]["tool_name"], names)
        search = next(t for t in entries if t["name"] == "invoice.search")
        self.assertEqual(search["input_schema"]["properties"]["include_withdrawn"]["type"], "boolean")

    def test_fikcyjne_rachunki_i_granice_policzone_deterministycznie(self):
        case = self.examples["finance_case"]
        today = date.fromisoformat(case["reference_date"])
        records = [r for r in case["invoices"] if not r["withdrawn"]]
        unpaid = [r for r in records if r["status"] == "do_zaplaty"]
        expected = case["expected"]
        self.assertEqual(sum(r["amount_grosze"] for r in unpaid), expected["unpaid_total_grosze"])
        self.assertEqual(sum(r["amount_grosze"] for r in unpaid if date.fromisoformat(r["due_date"]) < today), expected["overdue_total_grosze"])
        self.assertEqual(sum(r["amount_grosze"] for r in unpaid if 0 <= (date.fromisoformat(r["due_date"]) - today).days <= 7), expected["due_soon_7_days_grosze"])
        self.assertEqual(sum(r["amount_grosze"] for r in records if r["status"] == "oplacony" and r["paid_date"] and r["paid_date"].startswith("2026-11")), expected["cashflow_2026_11_grosze"])
        ids = {r["id"] for r in records}
        missing = [p["profile_id"] for p in case["expected_profiles"] if not (ids & set(p["matched_invoice_ids"])) and date.fromisoformat(p["expected_from"]) <= today]
        self.assertEqual(missing, expected["missing_profile_ids"])
        self.assertTrue(any(r["status"] == "oplacony" and r["paid_date"] is None for r in records))
        self.assertTrue(any(r["withdrawn"] for r in case["invoices"]))

    def test_propozycje_nie_daja_prawa_zapisu(self):
        action = self.examples["analysis_result"]["proposed_actions"][0]
        self.assertTrue(action["requires_confirmation"])
        self.assertEqual(action["expected_data_revision"], self.examples["task_request"]["data_revision"])
        self.assertFalse(any(entry["effect"] != "read" for entry in self.tools["tools"]))


if __name__ == "__main__":
    unittest.main()
