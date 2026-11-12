# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Ostrożne rozpoznawanie podobnych nazw kategorii bez zewnętrznych bibliotek."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from collections.abc import Iterable


PODSTAWOWE_KATEGORIE = frozenset({
    "Energia elektryczna", "Gaz", "Czynsz", "Telefon",
    "Fundusz remontowy", "Inne",
})


def klucz_kategorii(nazwa: str) -> str:
    """Ignoruj wielkość liter, diakrytyki, myślniki i zbędne spacje.

    Klucz służy wyłącznie do wykrywania prawdopodobnych duplikatów.
    Nie zmienia istniejących nazw ani przypisań w SQLite.
    """
    normal = unicodedata.normalize("NFKD", nazwa.casefold()).replace("ł", "l")
    bez_akcentow = "".join(c for c in normal if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", bez_akcentow))


def podobne_kategorie(nazwa: str, istniejace: Iterable[str]) -> list[str]:
    """Podpowiedzi, a nie automatyczne utożsamianie różnych kategorii.

    Ostrzegamy o bliskiej literówce, identycznym początku słowa lub wspólnym
    pierwszym wyrazie (np. 'Energia' vs 'Energia elektryczna').
    """
    klucz = klucz_kategorii(nazwa)
    if not klucz:
        return []
    first = klucz.split()[0]
    found: list[tuple[float, str]] = []
    for original in istniejace:
        other = klucz_kategorii(original)
        if not other:
            continue
        first_other = other.split()[0]
        similarity = SequenceMatcher(None, klucz, other).ratio()
        first_similarity = SequenceMatcher(None, first, first_other).ratio()
        closely_related = (
            min(len(first), len(first_other)) >= 5
            and (first.startswith(first_other[:5]) or first_other.startswith(first[:5]))
            and first_similarity >= 0.70
        )
        if other == klucz or similarity >= 0.77 or closely_related:
            found.append((1.0 if other == klucz else
                          max(similarity, first_similarity), original))
    return [label for _, label in sorted(
        found, key=lambda item: (-item[0], item[1].casefold())
    )[:5]]
