# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Deterministyczna kontrola IBAN/NRB i NIP, niezależna od lokalnego LLM."""
from __future__ import annotations

import re


def normalizuj_iban(wartosc: str) -> str:
    """Usuń wyłącznie odstępy, nie zmieniaj cyfr ani liter rachunku."""
    return re.sub(r"\s+", "", wartosc).upper()


def poprawny_iban(wartosc: str) -> bool:
    """Kontrola sumy modulo 97; obsługuje polski NRB i zapis IBAN."""
    numer = normalizuj_iban(wartosc)
    if re.fullmatch(r"[0-9]{26}", numer):
        numer = "PL" + numer
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", numer):
        return False
    if numer.startswith("PL") and len(numer) != 28:
        return False
    if not (15 <= len(numer) <= 34):
        return False
    przestawiony = numer[4:] + numer[:4]
    reszta = 0
    for znak in przestawiony:
        zawartosc = znak if znak.isdigit() else str(ord(znak) - ord("A") + 10)
        for cyfra in zawartosc:
            reszta = (reszta * 10 + int(cyfra)) % 97
    return reszta == 1


def zweryfikuj_numer_konta(wartosc: str) -> str:
    """Pusty numer jest dopuszczalny; niepusty wymaga poprawnej sumy."""
    numer = normalizuj_iban(wartosc)
    if not numer:
        return ""
    if not poprawny_iban(numer):
        raise ValueError(
            "Niepoprawny numer konta (NRB/IBAN lub suma kontrolna). "
            "Sprawdź go z oryginalnym rachunkiem."
        )
    return numer


def normalizuj_nip(value: str) -> str | None:
    """Zwróć 10 cyfr tylko dla NIP-u z poprawną sumą kontrolną."""
    digits = re.sub(r"[\s-]", "", value)
    if not re.fullmatch(r"[0-9]{10}", digits) or digits == "0000000000":
        return None
    factors = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    check = sum(int(a) * w for a, w in zip(digits, factors)) % 11
    return digits if check == int(digits[-1]) else None
