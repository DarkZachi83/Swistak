# SPDX-License-Identifier: GPL-3.0-only
"""Testy normalizacji zaznaczenia (działają bez Qt)."""
import unittest

from uslugi.geometria import Zaznaczenie, zaznaczenie_z_pikseli


class TestGeometria(unittest.TestCase):
    def test_zwykly_prostokat(self):
        wynik = zaznaczenie_z_pikseli(0, (100, 200), (500, 700), 1000, 1000)
        self.assertEqual(wynik, Zaznaczenie(0, .1, .2, .5, .7))

    def test_przeciaganie_w_druga_strone(self):
        wynik = zaznaczenie_z_pikseli(3, (500, 700), (100, 200), 1000, 1000)
        self.assertEqual(wynik, Zaznaczenie(3, .1, .2, .5, .7))

    def test_dociecie_poza_strona(self):
        wynik = zaznaczenie_z_pikseli(0, (-20, -10), (1200, 1100), 1000, 1000)
        self.assertEqual(wynik, Zaznaczenie(0, 0, 0, 1, 1))

    def test_zbyt_maly_prostokat(self):
        wynik = zaznaczenie_z_pikseli(0, (3, 2), (5, 12), 1000, 1000)
        self.assertIsNone(wynik)

    def test_brak_wymiarow(self):
        with self.assertRaises(ValueError):
            zaznaczenie_z_pikseli(0, (0, 0), (20, 20), 0, 100)

    def test_ta_sama_pozycja_w_roznych_rozdzielczosciach(self):
        a = zaznaczenie_z_pikseli(1, (100, 200), (300, 400), 1000, 1000)
        b = zaznaczenie_z_pikseli(1, (200, 400), (600, 800), 2000, 2000)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
