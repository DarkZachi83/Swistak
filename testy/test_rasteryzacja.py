# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Testy rzeczywistej ekstrakcji OCR ze sztucznych obrazkowych PDF."""
from __future__ import annotations

import importlib.util
import shutil
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

from uslugi.geometria import Zaznaczenie
from uslugi.odczyt_pdf import odczytaj_pdf
from uslugi.rasteryzacja import rasteryzuj_strone
from tools.porownaj_ocr import KONTO_TESTOWE, WZORCE, generuj_skan, normalizuj_tekst


class TestRasteryzacja(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.pdf = Path(cls.temp.name) / "skan-tylko-obraz.pdf"
        cls.wiersze = WZORCE[0][3]
        generuj_skan(cls.pdf, cls.wiersze)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_generowanie_skanu_bez_systemowego_dejavu(self):
        """Generator działa również bez DejaVuSans.ttf w katalogach systemowych."""
        from unittest.mock import patch
        from PIL import ImageFont

        oryginalny_truetype = ImageFont.truetype

        def bez_dejavu(font, size, *args, **kwargs):
            if font == "DejaVuSans.ttf":
                raise OSError("cannot open resource")
            return oryginalny_truetype(font, size, *args, **kwargs)

        cel = Path(self.temp.name) / "bez-dejavu.pdf"
        with patch("tools.porownaj_ocr.ImageFont.truetype", side_effect=bez_dejavu):
            generuj_skan(cel, self.wiersze, rozmiar_pisma=34)
        self.assertTrue(cel.is_file())
        with rasteryzuj_strone(cel, 0, 220, "pdfium") as obraz:
            self.assertGreater(obraz.width, 1000)
            self.assertGreater(obraz.height, 1200)

    def test_strona_jest_obrazem_pdfium(self):
        with rasteryzuj_strone(self.pdf, 0, 220, "pdfium") as obraz:
            self.assertGreater(obraz.width, 1000)
            self.assertGreater(obraz.height, 1200)
            self.assertEqual(obraz.mode, "RGB")

    def test_walidacja_silnika_i_numeru_strony(self):
        for blad in ((-1, 220, "pdfium"), (0, 20, "pdfium"),
                     (0, 220, "nie_istnieje")):
            with self.assertRaises(ValueError):
                rasteryzuj_strone(self.pdf, *blad)

    @unittest.skipUnless(shutil.which("tesseract"), "Brak lokalnego Tesseract")
    def test_prawdziwy_ocr_pdfium(self):
        wynik = odczytaj_pdf(self.pdf, silnik_rasteryzacji="pdfium", jezyk="pol+eng")
        self.assertEqual(wynik.strony[0].metoda, "ocr")
        tekst = normalizuj_tekst(wynik.strony[0].tekst)
        self.assertIn("189,50", tekst)
        self.assertIn("2026-12-01", tekst)
        self.assertIn(normalizuj_tekst(KONTO_TESTOWE), tekst)

    @unittest.skipUnless(shutil.which("tesseract"), "Brak lokalnego Tesseract")
    def test_ocr_zaznaczenia_pdfium(self):
        # Kwota zajmuje w naszym obrazie trzeci wiersz
        wycinek = Zaznaczenie(0, 0.0, 0.16, 0.99, 0.25)
        wynik = odczytaj_pdf(
            self.pdf, wycinek, silnik_rasteryzacji="pdfium", jezyk="pol+eng"
        )
        self.assertEqual(len(wynik.strony), 1)
        self.assertEqual(wynik.strony[0].metoda, "ocr")
        self.assertIn("189,50", normalizuj_tekst(wynik.strony[0].tekst))

    @unittest.skipUnless(shutil.which("tesseract") and shutil.which("pdftoppm")
                         and importlib.util.find_spec("pdf2image"),
                         "Brak opcjonalnego Popplera lub pdf2image")
    def test_poppler_odczytuje_ten_sam_skan(self):
        wynik = odczytaj_pdf(self.pdf, silnik_rasteryzacji="poppler")
        self.assertEqual(wynik.strony[0].metoda, "ocr")
        self.assertIn("189,50", normalizuj_tekst(wynik.strony[0].tekst))

    def test_wiele_watkow_pdfium_jest_serializowane(self):
        """Test czterech równoczesnych operacji bez uruchamiania PDFium.

        Fałszywy renderer wykrywa nakładanie się żywych dokumentów.
        """
        from PIL import Image

        aktywne = 0
        maks_aktywne = 0
        licznik = threading.Lock()
        bariera = threading.Barrier(4)

        class FalszywaBitmapa:
            def to_pil(self):
                return Image.new("RGB", (12, 12), "white")

            def close(self):
                pass

        class FalszywaStrona:
            def render(self, **kwargs):
                time.sleep(0.025)
                return FalszywaBitmapa()

            def close(self):
                pass

        class FalszywyDokument:
            def __init__(self, nazwa):
                self.nazwa = nazwa

            def __enter__(self):
                nonlocal aktywne, maks_aktywne
                with licznik:
                    aktywne += 1
                    maks_aktywne = max(maks_aktywne, aktywne)
                return self

            def __len__(self):
                return 1

            def __getitem__(self, numer):
                return FalszywaStrona()

            def __exit__(self, *args):
                nonlocal aktywne
                with licznik:
                    aktywne -= 1

        fake = types.ModuleType("pypdfium2")
        fake.PdfDocument = FalszywyDokument

        def praca():
            bariera.wait(timeout=5)
            with rasteryzuj_strone(self.pdf, 0, 180) as obraz:
                return obraz.size

        with patch.dict(sys.modules, {"pypdfium2": fake}):
            with ThreadPoolExecutor(max_workers=4) as pool:
                wyniki = list(pool.map(lambda _: praca(), range(4)))
        self.assertEqual(wyniki, [(12, 12)] * 4)
        self.assertEqual(maks_aktywne, 1)
        self.assertEqual(aktywne, 0)

    def test_pdfium_wymaga_zero_programow_poppler(self):
        # Sprawdzamy, czy renderer domyślny nie sięga po funkcję pdf2image:
        with patch("sys.modules", {"pdf2image": None}):
            with rasteryzuj_strone(self.pdf, 0, 180) as obraz:
                self.assertGreater(obraz.width, 0)


if __name__ == "__main__":
    unittest.main()
