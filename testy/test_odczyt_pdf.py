# SPDX-License-Identifier: GPL-3.0-only
"""Warstwa PDF/OCR; wszystkie dokumenty syntetyczne."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter

from uslugi.geometria import Zaznaczenie
from uslugi.odczyt_pdf import BladOdczytu, OdczytAnulowany, odczytaj_pdf


class TestOdczytPDF(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plik = Path(self.tmp.name) / "syntetyczny.pdf"
        pdf = QPdfWriter(str(self.plik))
        pdf.setResolution(72)  # współrzędne w punktach, bez nakładania wierszy
        p = QPainter(pdf)
        self.assertTrue(p.isActive())
        p.drawText(100, 150, "FAKTURA TESTOWA ZAKLAD DEMO")
        p.drawText(100, 190, "KWOTA DO ZAPLATY 125 PLN")
        self.assertTrue(p.end())

    def tearDown(self):
        self.tmp.cleanup()

    def test_cala_strona_warstwa_tekstowa(self):
        wynik = odczytaj_pdf(self.plik, z_ocr=False)
        self.assertEqual(len(wynik.strony), 1)
        self.assertEqual(wynik.strony[0].metoda, "tekst")
        self.assertIn("TESTOWA", wynik.tekst_dla_llm)
        self.assertIn("STRONA 1", wynik.tekst_dla_llm)

    def test_ocr_tylko_gdy_brak_tekstu(self):
        with patch("uslugi.odczyt_pdf._uruchom_ocr") as mock_ocr:
            wynik = odczytaj_pdf(self.plik)
        self.assertEqual(wynik.strony[0].metoda, "tekst")
        mock_ocr.assert_not_called()

    def test_sztuczna_strona_bez_warstwy_tekstowej(self):
        pusta = Path(self.tmp.name) / "pusta.pdf"
        pdf = QPdfWriter(str(pusta))
        pdf.setResolution(72)
        p = QPainter(pdf)
        p.drawRect(100, 100, 250, 150)
        p.end()
        with patch("uslugi.odczyt_pdf._uruchom_ocr", return_value="Tekst zeskanowany") as mock:
            wynik = odczytaj_pdf(pusta)
        self.assertEqual(wynik.strony[0].metoda, "ocr")
        self.assertEqual(wynik.strony[0].tekst, "Tekst zeskanowany")
        mock.assert_called_once()

    def test_zaznaczenie_jednej_strony(self):
        region = Zaznaczenie(0, 0.01, 0.01, 0.9, 0.5)
        wynik = odczytaj_pdf(self.plik, region, z_ocr=False)
        self.assertEqual(len(wynik.strony), 1)
        self.assertIn("TESTOWA", wynik.tekst_dla_llm)

    def test_bledny_region(self):
        with self.assertRaises(ValueError):
            odczytaj_pdf(self.plik, Zaznaczenie(0, .8, .2, .1, .8), z_ocr=False)

    def test_strona_nie_istnieje(self):
        with self.assertRaises(BladOdczytu):
            odczytaj_pdf(self.plik, Zaznaczenie(8, .1, .1, .8, .8))

    def test_anulowanie(self):
        przerwij = threading.Event()
        przerwij.set()
        with self.assertRaises(OdczytAnulowany):
            odczytaj_pdf(self.plik, przerwij=przerwij)

    def test_limity(self):
        with self.assertRaises(ValueError):
            odczytaj_pdf(self.plik, dpi=20)
        with self.assertRaises(ValueError):
            odczytaj_pdf(self.plik, maks_stron=0)
