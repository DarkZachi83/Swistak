# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Współrzędne zaznaczenia PDF niezależne od powiększenia okna."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Zaznaczenie:
    """Ułamki szerokości/wysokości strony (w zakresie 0..1)."""

    strona: int   # numer strony od zera, zgodnie z QPdfDocument
    lewo: float
    gora: float
    prawo: float
    dol: float


def ogranicz(wartosc: float, maksimum: float) -> float:
    return max(0.0, min(wartosc, maksimum))


def zaznaczenie_z_pikseli(
    strona: int,
    poczatek: tuple[float, float],
    koniec: tuple[float, float],
    szerokosc: float,
    wysokosc: float,
    minimum_pikseli: float = 3.0,
) -> Zaznaczenie | None:
    """Zwraca prostokąt normalizowany lub None dla zbyt małego zaznaczenia.

    Wejściowe współrzędne mierzymy na *wyrenderowanym obrazie strony*, a nie
    w pikselach ekranu. Funkcja przyjmuje przeciąganie w każdym kierunku,
    a pozycje wychodzące poza obraz docina do granic strony.
    """
    if szerokosc <= 0 or wysokosc <= 0:
        raise ValueError("Wymiary strony muszą być dodatnie")
    x0 = ogranicz(min(poczatek[0], koniec[0]), szerokosc)
    x1 = ogranicz(max(poczatek[0], koniec[0]), szerokosc)
    y0 = ogranicz(min(poczatek[1], koniec[1]), wysokosc)
    y1 = ogranicz(max(poczatek[1], koniec[1]), wysokosc)
    if (x1 - x0) < minimum_pikseli or (y1 - y0) < minimum_pikseli:
        return None
    return Zaznaczenie(strona, x0 / szerokosc, y0 / wysokosc,
                       x1 / szerokosc, y1 / wysokosc)
