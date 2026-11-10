# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Schemat JSON i test bez wykonywania żądania do Ollamy."""
from __future__ import annotations
import io
import json
import unittest
from unittest.mock import patch

from tools.test_gemma import FORMAT, POLA, TEKST_DEMO, wywolaj_model


class TestGemma(unittest.TestCase):
    @staticmethod
    def poprawny_json():
        return {
            p: {"wartosc": None, "dowod": None}
            for p in POLA
        }

    def test_format_wymusza_wszystkie_pola(self):
        self.assertEqual(set(FORMAT["required"]), set(POLA))
        self.assertFalse(FORMAT["additionalProperties"])

    def test_zadanie_jest_lokalne_i_bez_zapisu(self):
        wynik = self.poprawny_json()
        wynik["dostawca"] = {"wartosc": "Zakład Gazowy DEMO",
                             "dowod": "Sprzedawca: Zakład Gazowy DEMO"}
        odpowiedz = {"message": {"content": json.dumps(wynik)}}
        context = unittest.mock.MagicMock()
        context.__enter__.return_value = io.BytesIO(json.dumps(odpowiedz).encode())
        with patch("tools.test_gemma.urlopen", return_value=context) as url:
            dane = wywolaj_model(TEKST_DEMO)
        self.assertEqual(dane["dostawca"]["wartosc"], "Zakład Gazowy DEMO")
        req = url.call_args[0][0]
        self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/chat")
        body = json.loads(req.data)
        self.assertEqual(body["model"], "gemma3:4b")
        self.assertFalse(body["stream"])
        self.assertIn("format", body)

    def test_hallucynowany_dowod_jest_odrzucony(self):
        wynik = self.poprawny_json()
        wynik["dostawca"] = {"wartosc": "Nieistniejąca firma", "dowod": "Tekst którego nie ma"}
        odpowiedz = {"message": {"content": json.dumps(wynik)}}
        context = unittest.mock.MagicMock()
        context.__enter__.return_value = io.BytesIO(json.dumps(odpowiedz).encode())
        with patch("tools.test_gemma.urlopen", return_value=context):
            with self.assertRaises(ValueError):
                wywolaj_model(TEKST_DEMO)

    def test_puste_dane(self):
        with self.assertRaises(ValueError):
            wywolaj_model(" \n ")


if __name__ == "__main__":
    unittest.main()
