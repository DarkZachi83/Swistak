# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Regresja przełączania języków: przejęte podejście, nie kod AI Bobra."""
from __future__ import annotations

import json
import string
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import i18n
import ustawienia


class TestSlowniki(unittest.TestCase):
    def setUp(self):
        root = Path(i18n.__file__).parent
        self.pl = json.loads((root / "pl.json").read_text(encoding="utf-8"))
        self.en = json.loads((root / "en.json").read_text(encoding="utf-8"))

    def tearDown(self):
        i18n.set_language("pl")

    def test_klucze_i_pola_formatowania(self):
        self.assertEqual(set(self.pl), set(self.en))
        for key in self.pl:
            self.assertTrue(self.pl[key].strip(), key)
            self.assertTrue(self.en[key].strip(), key)
            def fields(text):
                return {name for _, name, _, _ in string.Formatter().parse(text)
                        if name is not None}
            self.assertEqual(fields(self.pl[key]), fields(self.en[key]), key)

    def test_kazdy_jezyk_przelacza_widoczne_napisy(self):
        self.assertEqual(i18n.set_language("pl"), "pl")
        self.assertEqual(i18n.t("menu.language"), "Języki")
        self.assertEqual(i18n.set_language("en"), "en")
        self.assertEqual(i18n.t("menu.language"), "Languages")
        self.assertIn("4", i18n.t("ai.done", model="gemma3:4b", count=4, total=10))
        self.assertEqual(i18n.t("missing.key"), "missing.key")

    def test_system_language_bobr_pattern(self):
        sl = i18n.system_language
        self.assertEqual(sl({"LANG": "pl_PL.UTF-8"}), "pl")
        self.assertEqual(sl({"LC_ALL": "C.UTF-8", "LANG": "pl_PL.UTF-8"}), "pl")
        self.assertEqual(sl({"LC_MESSAGES": "en_US.UTF-8", "LANG": "pl_PL.UTF-8"}), "en")
        self.assertEqual(sl({"LC_ALL": "POSIX", "LANG": "en_US.UTF-8"}), "en")
        self.assertEqual(sl({"LANG": "Polish_Poland.1250"}), "pl")
        with patch.object(i18n, "system_language", return_value="en"):
            self.assertEqual(i18n.set_language(""), "en")
        with patch.object(i18n, "system_language", return_value="pl"):
            self.assertEqual(i18n.set_language(None), "pl")


class TestUstawienia(unittest.TestCase):
    def test_trwale_zapisywanie_oddzielnie_od_bazy(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "settings.json"
            self.assertEqual(ustawienia.load(path)["language"], "")
            ustawienia.save({"language": "en", "ollama_model": "gemma3:4b"}, path)
            self.assertEqual(ustawienia.load(path)["language"], "en")
            self.assertEqual(ustawienia.load(path)["ollama_model"], "gemma3:4b")
            self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))
            ustawienia.save({"language": "", "ollama_model": "qwen3:4b"}, path)
            self.assertEqual(ustawienia.load(path)["ollama_model"], "qwen3:4b")

    def test_uszkodzone_ustawienia_i_niewlasciwy_model(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "settings.json"
            path.write_text("!!!", encoding="utf-8")
            self.assertEqual(ustawienia.load(path), ustawienia.DEFAULTS)
            with self.assertRaises(ValueError):
                ustawienia.save({"language": "fr", "ollama_model": "gemma3:4b"}, path)
            with self.assertRaises(ValueError):
                ustawienia.save({"language": "pl", "ollama_model": ""}, path)


if __name__ == "__main__":
    unittest.main()
