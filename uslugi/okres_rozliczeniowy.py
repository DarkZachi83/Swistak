# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Deterministyczny okres rozliczeniowy z bieżącego OCR/PDF.

Nie używamy daty wystawienia, terminu płatności ani treści wzorca jako
źródła okresu. Naprawa następuje tylko dla JEDNEGO jednoznacznego
miesiąca rozliczeniowego (MM/RRRR) w opisach usług.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

_MIESIAC = re.compile(
    r"(?<![\w/.-])(?P<miesiac>0?[1-9]|1[0-2])/(?P<rok>20\d{2})(?![\w/.-])"
)
_KONTEKST = (
    "okres", "rozliczen", "abonament", "uslug", "internet", "linia",
    "linii", "utrzyman", "pakiet", "polaczen", "swiatlowod",
)


@dataclass(frozen=True)
class MiesiacRozliczenia:
    od: str
    do: str
    dowod: str  # istniejący, dosłowny fragment bieżącego PDF / OCR


def _uprosc(text: str) -> str:
    # NFKD nie rozkłada polskiego ł; bez tego etykieta "Usługa" znika z kontekstu.
    value = unicodedata.normalize("NFKD", text.lower()).replace("ł", "l")
    return "".join(letter for letter in value if not unicodedata.combining(letter))


def rozpoznaj_miesiac_rozliczenia(tekst: str) -> MiesiacRozliczenia | None:
    """Wiele różnych miesięcy = niejednoznaczność, oddaj decyzję człowiekowi."""
    matched: dict[tuple[int, int], str] = {}
    for line in tekst.splitlines():
        line = line.strip()
        if not line or not any(term in _uprosc(line) for term in _KONTEKST):
            continue
        for found in _MIESIAC.finditer(line):
            month, year = int(found["miesiac"]), int(found["rok"])
            if year < 2000 or year > 2099:
                continue
            matched.setdefault((year, month), line[:240])
    if len(matched) != 1:
        return None
    (year, month), source = next(iter(matched.items()))
    last = calendar.monthrange(year, month)[1]
    return MiesiacRozliczenia(
        date(year, month, 1).isoformat(),
        date(year, month, last).isoformat(),
        source,
    )


def popraw_okres_modelu(wynik: dict, tekst: str) -> tuple[dict, set[str]]:
    """Koryguj tylko daty z odpowiedzi modelu, a nie późniejsze edycje człowieka."""
    month = rozpoznaj_miesiac_rozliczenia(tekst)
    if month is None:
        return wynik, set()
    corrected = {key: dict(value) for key, value in wynik.items()}
    changed = set()
    for name, expected in (("okres_od", month.od), ("okres_do", month.do)):
        if name not in corrected or not isinstance(corrected[name], dict):
            continue
        if corrected[name].get("wartosc") != expected:
            changed.add(name)
        corrected[name]["wartosc"] = expected
        corrected[name]["dowod"] = month.dowod
    return corrected, changed
