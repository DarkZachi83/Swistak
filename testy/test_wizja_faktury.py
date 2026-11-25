# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Testy analizy obrazu faktury bez prywatnych danych i prawdziwej Ollamy."""
from __future__ import annotations

import json
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from PIL import Image

from ai_core.errors import ModelUnavailable
from ai_core.ollama import OllamaProvider
from uslugi.analiza_ai_core import analizuj_przez_ai_core
from uslugi.analiza_llm import POLA
from uslugi.wizja_pdf import MAKS_STRON_WIZJI, przygotuj_obrazy_faktury


def pola():
    result = {name: {"wartosc": None, "dowod": None} for name in POLA}
    result["dostawca"] = {
        "wartosc": "Syntetyczna Energia",
        "dowod": "Sprzedawca: Syntetyczna Energia",
    }
    result["kwota_do_zaplaty"] = {
        "wartosc": "124,50", "dowod": "Kwota do zapłaty: 124,50 PLN",
    }
    result["waluta"] = {"wartosc": "PLN", "dowod": "124,50 PLN"}
    return result


class TestWizjaPDF(unittest.TestCase):
    def test_rasteryzacja_wszystkich_stron(self):
        with (patch("pathlib.Path.is_file", return_value=True),
              patch("pypdfium2.PdfDocument") as pdf,
              patch("uslugi.wizja_pdf.rasteryzuj_strone",
                    side_effect=lambda *_a, **_k: Image.new("RGB", (30, 40), "white"))
              as raster):
            pdf.return_value.__enter__.return_value.__len__.return_value = 2
            obrazy = przygotuj_obrazy_faktury(Path("/syntetyczny.pdf"))
        self.assertEqual(len(obrazy), 2)
        self.assertEqual(raster.call_count, 2)
        self.assertTrue(all(image.startswith("/9j/") for image in obrazy))

    def test_limit_stron_nie_ukrywa_fragmentu_faktury(self):
        with (patch("pathlib.Path.is_file", return_value=True),
              patch("pypdfium2.PdfDocument") as pdf,
              patch("uslugi.wizja_pdf.rasteryzuj_strone") as raster):
            pdf.return_value.__enter__.return_value.__len__.return_value = MAKS_STRON_WIZJI + 1
            with self.assertRaisesRegex(ValueError, "Nie pominięto"):
                przygotuj_obrazy_faktury(Path("/syntetyczny.pdf"))
            raster.assert_not_called()


class TestEkstrakcjaWizyjna(unittest.TestCase):
    def setUp(self):
        self.provider = OllamaProvider(timeout=5)
        self.caps = {
            "model_info": {"test.context_length": 32768},
            "capabilities": ["completion", "vision"],
        }
        self.reply = {
            "message": {"content": json.dumps(pola())},
            "prompt_eval_count": 1600,
        }

    def test_faktura_bez_ocr_jest_analizowana_z_obrazow(self):
        with (patch("uslugi.analiza_ai_core.przygotuj_obrazy_faktury",
                    return_value=["ZmFrZQ=="]),
              patch.object(self.provider, "_request",
                           side_effect=[self.caps, self.reply]) as requests):
            wynik = analizuj_przez_ai_core(
                "", ["Energia"], provider=self.provider,
                sciezka_pdf=Path("/syntetyczny.pdf"),
            )
        self.assertEqual(wynik.zrodlo, "obraz")
        self.assertEqual(wynik.oceny["kwota_do_zaplaty"].wartosc, "124,50")
        self.assertFalse(wynik.oceny["kwota_do_zaplaty"].poprawne)
        self.assertIn("OCR", wynik.oceny["dostawca"].komunikat)
        payload = requests.call_args.args[1]
        self.assertEqual(payload["messages"][-1]["images"], ["ZmFrZQ=="])
        self.assertIn("OBRAZY", payload["messages"][-1]["content"])
        self.assertNotIn("tools", payload)

    def test_ocr_jest_niezaleznym_potwierdzeniem(self):
        tekst = "Sprzedawca: Syntetyczna Energia\nKwota do zapłaty: 124,50 PLN"
        with (patch("uslugi.analiza_ai_core.przygotuj_obrazy_faktury",
                    return_value=["ZmFrZQ=="]),
              patch.object(self.provider, "_request",
                           side_effect=[self.caps, self.reply]) as request):
            wynik = analizuj_przez_ai_core(
                tekst, ["Energia"], provider=self.provider,
                sciezka_pdf=Path("/syntetyczny.pdf"),
            )
        self.assertTrue(wynik.oceny["kwota_do_zaplaty"].poprawne)
        # OCR weryfikuje lokalnie gotowy wynik; nie jest podpowiedzią dla VLM.
        self.assertNotIn("124,50", request.call_args.args[1]["messages"][-1]["content"])

    def test_gemma3_analizuje_obraz_mimo_niepelnych_capabilities(self):
        for show in (
            {"model_info": {"test.context_length": 32768},
             "capabilities": ["completion"]},
            {"model_info": {"test.context_length": 32768}},
            {"model_info": {"test.context_length": 32768},
             "capabilities": []},
        ):
            with self.subTest(show=show):
                with (patch("uslugi.analiza_ai_core.przygotuj_obrazy_faktury",
                            return_value=["ZmFrZQ=="]),
                      patch.object(self.provider, "_request",
                                   side_effect=[show, self.reply]) as requests):
                    wynik = analizuj_przez_ai_core(
                        "", ["Energia"], model="gemma3:4b",
                        provider=self.provider,
                        sciezka_pdf=Path("/syntetyczny.pdf"),
                    )
                self.assertEqual(wynik.zrodlo, "obraz")
                self.assertEqual(requests.call_count, 2)
                self.assertEqual(requests.call_args.args[0], "/api/chat")
                self.assertEqual(requests.call_args.args[1]["messages"][-1]["images"],
                                 ["ZmFrZQ=="])

    def test_blad_api_show_nie_blokuje_wyslania_obrazu(self):
        with (patch("uslugi.analiza_ai_core.przygotuj_obrazy_faktury",
                    return_value=["ZmFrZQ=="]),
              patch.object(self.provider, "_request",
                           side_effect=[ModelUnavailable("brak metadanych"),
                                        self.reply]) as requests):
            wynik = analizuj_przez_ai_core(
                "", ["Energia"], model="gemma3:4b",
                provider=self.provider, sciezka_pdf=Path("/syntetyczny.pdf"),
            )
        self.assertEqual(wynik.zrodlo, "obraz")
        self.assertEqual(requests.call_count, 2)
        self.assertEqual(requests.call_args.args[0], "/api/chat")

    def test_rzeczywiste_odrzucenie_obrazu_przez_ollame_ma_jasny_blad(self):
        error_text = b'{"error":"model does not support images, SECRET-INVOICE"}'
        error = HTTPError(
            "http://127.0.0.1:11434/api/chat", 400, "Bad Request",
            {}, BytesIO(error_text),
        )
        request = {
            "model": "model-tekstowy", "stream": False, "truncate": False,
            "messages": [{"role": "user", "content": "syntetyczny dokument",
                          "images": ["ZmFrZQ=="]}],
        }
        with patch.object(self.provider._opener, "open", side_effect=error):
            with self.assertRaisesRegex(ModelUnavailable, "HTTP 400") as ctx:
                self.provider._request("/api/chat", request)
        self.assertNotIn("SECRET-INVOICE", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
