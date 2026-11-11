# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Dopasowanie zatwierdzonego wzorca: NIP (60) + sprzedawca (20) + układ (20)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from uslugi.wzorce import nowy_wzorzec

# Wyłącznie stałe publiczne etykiety, bez fragmentów nabywcy ani numerów kont.
ETYKIETY_UKLADU = (
    "Faktura nr", "Data wystawienia", "Termin płatności",
    "Konto bankowe", "Wartość faktury", "Kwota do zapłaty",
    "Okres rozliczeniowy", "Sprzedawca", "Data sprzedaży",
)
ETYKIETY_POL = {
    "dostawca": ["Sprzedawca"],
    "numer_faktury": ["Faktura nr", "Numer faktury"],
    "kwota_do_zaplaty": ["Wartość faktury", "Kwota do zapłaty"],
    "data_wystawienia": ["Data wystawienia"],
    "termin_platnosci": ["Termin płatności"],
    "okres_od": ["Okres", "Okres rozliczeniowy"],
    "okres_do": ["Okres", "Okres rozliczeniowy"],
    "numer_konta_bankowego": ["Konto bankowe", "Numer konta"],
}
NIP_RE = re.compile(r"\bNIP[\s:.-]*((?:\d[\s-]*){10})\b", re.IGNORECASE)


def uprosc(value: str) -> str:
    norm = unicodedata.normalize("NFKD", value.casefold())
    norm = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w]+", " ", norm).split())


def normalizuj_nip(value: str) -> str | None:
    digits = re.sub(r"[\s-]", "", value)
    if not re.fullmatch(r"\d{10}", digits) or digits == "0000000000":
        return None
    factors = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    check = sum(int(a) * w for a, w in zip(digits, factors)) % 11
    return digits if check != 10 and check == int(digits[-1]) else None


def sprzedawca_fragment(tekst: str) -> str:
    """NIP i alias tylko z sekcji sprzedawcy — nigdy z sekcji nabywcy."""
    match = re.search(
        r"(?im)^[ \t]*(?:sprzedawca|wystawca|seller)(?:[ \t]*:|[ \t]*(?=\r?$))",
        tekst,
    )
    if not match:
        return ""  # bezpieczeństwo: brak sekcji => brak pewnego NIP-u
    fragment = tekst[match.end():match.end() + 1200]
    koniec = re.search(
        r"(?i)\b(?:nabywca|odbiorca|buyer|płatnik|platnik)\s*:",
        fragment,
    )
    return fragment[:koniec.start()] if koniec else fragment[:500]


def cechy_dokumentu(tekst: str) -> dict:
    seller = sprzedawca_fragment(tekst)
    nip = None
    if match := NIP_RE.search(seller):
        nip = normalizuj_nip(match.group(1))
    label_text = uprosc(tekst)
    return {
        "seller_nip": nip,
        "seller_text": uprosc(seller),
        "layout_labels": [
            label for label in ETYKIETY_UKLADU
            if uprosc(label) in label_text
        ],
    }


@dataclass(frozen=True)
class Dopasowanie:
    wzorzec: dict
    punkty: int
    poziom: str  # automatic / suggest


def dopasuj(tekst: str, wzorce: list[dict]) -> Dopasowanie | None:
    cechy = cechy_dokumentu(tekst)
    punkty = []
    for template in wzorce:
        if template["status"] != "approved":
            continue
        ident = template["identification"]
        nip_wzorca, nip_tekst = ident["seller_nip"], cechy["seller_nip"]
        if nip_wzorca and nip_tekst and nip_wzorca != nip_tekst:
            continue  # sprzeczny NIP blokuje dopasowanie
        nip_ok = bool(nip_wzorca and nip_tekst and nip_wzorca == nip_tekst)
        alias_ok = any(uprosc(alias) in cechy["seller_text"]
                       for alias in ident["seller_aliases"] if uprosc(alias))
        etykiety = ident["layout_labels"]
        obecne = sum(uprosc(label) in uprosc(tekst) for label in etykiety)
        layout = round(20 * obecne / len(etykiety)) if etykiety else 0
        score = (60 if nip_ok else 0) + (20 if alias_ok else 0) + layout
        if score:
            punkty.append((score, nip_ok, alias_ok, template))
    if not punkty:
        return None
    punkty.sort(key=lambda item: (item[0], item[3]["template_id"]), reverse=True)
    score, nip_ok, alias_ok, best = punkty[0]
    competing = len(punkty) > 1 and punkty[1][0] >= score - 10
    # Sam NIP + nazwa (80 punktów) nie wystarczają do pewnego
    # zastosowania — ten sam operator może mieć różne układy faktur.
    if nip_ok and score >= 80 and layout >= 10 and not competing:
        return Dopasowanie(best, score, "automatic")
    # Bez NIP-u wolno tylko proponować, nawet z pełną zgodnością nazwy/układu.
    if score >= 55 or (alias_ok and score >= 30):
        return Dopasowanie(best, score, "suggest")
    return None


def zaproponuj_wzorzec(tekst: str, dostawca: str, kategoria: str | None,
                        uwagi_pol: dict[str, str] | None = None,
                        uwagi_ogolne: str = "") -> dict:
    """Buduj reguły, a NIE migawkę faktury. Tylko zatwierdzone opisy."""
    cechy = cechy_dokumentu(tekst)
    aliases = [dostawca.strip()] if dostawca.strip() else []
    rules = {}
    uwagi_pol = uwagi_pol or {}
    simplified = uprosc(tekst)
    for field, labels in ETYKIETY_POL.items():
        markers = [name for name in labels if uprosc(name) in simplified]
        note = uwagi_pol.get(field, "")
        if not markers and not note:
            continue
        source_format = ""
        target_format = ""
        if field in ("data_wystawienia", "termin_platnosci"):
            source_format, target_format = "DD.MM.RRRR", "RRRR-MM-DD"
        elif field in ("okres_od", "okres_do"):
            source_format, target_format = "MM/RRRR", "RRRR-MM-DD"
        elif field == "numer_konta_bankowego":
            target_format = "NRB_OR_IBAN"
        elif field == "kwota_do_zaplaty":
            target_format = "PLN"
        rules[field] = {
            "find_by": markers, "source_format": source_format,
            "target_format": target_format, "note": note,
        }
    for field, note in uwagi_pol.items():
        if field not in rules and note:
            rules[field] = {
                "find_by": [], "source_format": "", "target_format": "",
                "note": note,
            }
    notes = [uwagi_ogolne] if uwagi_ogolne.strip() else []
    return nowy_wzorzec(
        name=f"Faktura — {dostawca.strip()}",
        identification={
            "seller_nip": cechy["seller_nip"],
            "seller_aliases": aliases,
            "layout_labels": cechy["layout_labels"],
        },
        category=kategoria, fields=rules, agent_notes=notes,
    )
