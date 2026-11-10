# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Wstępny manifest PDFium: nie dowodzi pełnej zgodności licencyjnej."""
from __future__ import annotations

import unittest

from tools.sprawdz_pdfium import manifest_pdfium


class TestLicencjePDFium(unittest.TestCase):
    def test_manifest_zainstalowanego_wheel(self):
        wynik = manifest_pdfium()
        self.assertTrue(wynik["wersja_pypdfium2"])
        self.assertIsInstance(wynik["pliki_licencji"], list)
        self.assertIsInstance(wynik["binaria"], list)
        self.assertIsInstance(wynik["ostrzezenia"], list)


if __name__ == "__main__":
    unittest.main()
