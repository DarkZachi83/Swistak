# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Testy audytu licencji, działają bez połączenia z internetem."""
import unittest

from tools.audyt_licencji import sprawdz_rejestr, wymagane_pakiety


class TestAudytLicencji(unittest.TestCase):
    def test_wczytywanie_zakresow_wersji(self):
        self.assertEqual(
            wymagane_pakiety("PySide6>=6.8,<7\npdfplumber>=0.11,<1\n# komentarz\n"),
            {"pyside6", "pdfplumber"},
        )

    def test_odrzucanie_ukrytego_include(self):
        with self.assertRaises(ValueError):
            wymagane_pakiety("-r dodatkowe.txt\n")

    def test_wykrywa_niewpisany_pakiet(self):
        rejestr = {"schema_version": 1, "components": []}
        self.assertTrue(any("nie" in s.lower() or "brak" in s.lower()
                            for s in sprawdz_rejestr(rejestr, {"pyside6"})))

    def test_poprawna_rejestracja(self):
        rejestr = {
            "schema_version": 1,
            "components": [
                {
                    "name": "PySide6", "kind": "python-direct",
                    "license": "LGPL-3.0", "source_url": "https://example.com",
                    "status": "review", "purpose": "GUI",
                },
            ],
        }
        self.assertEqual(sprawdz_rejestr(rejestr, {"pyside6"}), [])


if __name__ == "__main__":
    unittest.main()
