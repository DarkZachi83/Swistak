# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Powtarzalne porównanie jakości OCR PDFium vs Poppler.

Tworzy WYŁĄCZNIE syntetyczne rachunki jako skany obrazkowe.
Nie czyta bazy użytkownika, nie łączy się z Ollamą, niczego nie wysyła.
Opcjonalny raport JSON zawiera tylko metryki, bez tekstu OCR.
Uruchomienie: python -m tools.porownaj_ocr --json raport_ocr.json
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from uslugi.odczyt_pdf import odczytaj_pdf

KONTO_TESTOWE = "61 1090 1014 0000 0712 1981 2874"
WZORCE = (
    ("czytelny", 34, 0, (
        "FAKTURA TESTOWA 15/11/2026",
        "Dostawca: Energia Domowa DEMO",
        "Kwota do zaplaty: 189,50 PLN",
        "Termin platnosci: 2026-12-01",
        "Numer konta: " + KONTO_TESTOWE,
        "Okres: 01.10.2026 - 31.10.2026",
    ), "189,50", "2026-12-01"),
    ("drobniejszy", 26, 90, (
        "FAKTURA VAT 22/11/2026",
        "Sprzedawca: Operator Testowy",
        "Faktura numer 2026/11/02",
        "Suma brutto: 350,50 PLN",
        "Kwota do zaplaty: 120,70 PLN",
        "Termin platnosci: 2026-11-28",
        "Numer konta: " + KONTO_TESTOWE,
    ), "120,70", "2026-11-28"),
)


def normalizuj_tekst(tekst: str) -> str:
    # Ignoruje różnice w grupowaniu cyfr i odstępach, nie usuwa cyfr.
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", tekst).casefold())


def generuj_skan(
    plik: Path, wiersze: tuple[str, ...],
    rozmiar_pisma: int = 34, szarosc: int = 0,
) -> None:
    """Wygeneruj jednostronicowy PDF zawierający tylko obraz, bez tekstu."""
    font = ImageFont.truetype("DejaVuSans.ttf", rozmiar_pisma)
    with Image.new("RGB", (1500, 2000), "white") as obraz:
        rysuj = ImageDraw.Draw(obraz)
        for numer, wiersz in enumerate(wiersze):
            rysuj.text(
                (70, 100 + numer * 135), wiersz, font=font,
                fill=(szarosc, szarosc, szarosc),
            )
        plik.parent.mkdir(parents=True, exist_ok=True)
        obraz.save(plik, "PDF", resolution=150.0)


def porownaj(silniki: tuple[str, ...] = ("pdfium", "poppler"), dpi: int = 220) -> dict:
    if not silniki or any(s not in ("pdfium", "poppler") for s in silniki):
        raise ValueError("Wybierz silnik pdfium albo poppler")
    pomiary = []
    with tempfile.TemporaryDirectory(prefix="swistak-ocr-benchmark-") as katalog:
        for nazwa, wielkosc, szarosc, wiersze, kwota, termin in WZORCE:
            pdf = Path(katalog) / (nazwa + ".pdf")
            generuj_skan(pdf, wiersze, wielkosc, szarosc)
            for silnik in silniki:
                start = time.perf_counter()
                wynik = odczytaj_pdf(pdf, dpi=dpi, silnik_rasteryzacji=silnik)
                sekundy = time.perf_counter() - start
                odczyt = wynik.strony[0].tekst
                tekst_porownania = normalizuj_tekst(odczyt)
                score = SequenceMatcher(
                    None, normalizuj_tekst(" ".join(wiersze)), tekst_porownania,
                    autojunk=False,
                ).ratio()
                # Obecność wartości w tekście, NIE dokładność interpretacji LLM.
                pola = {
                    "kwota": normalizuj_tekst(kwota) in tekst_porownania,
                    "termin_platnosci": normalizuj_tekst(termin) in tekst_porownania,
                    "cyfry_konta": normalizuj_tekst(KONTO_TESTOWE) in tekst_porownania,
                }
                pomiary.append({
                    "przypadek": nazwa, "silnik": silnik,
                    "metoda": wynik.strony[0].metoda,
                    "czas_sekundy": round(sekundy, 3),
                    "podobienstwo_znakow": round(score, 4),
                    "zgodnosc_wartosci": pola,
                })
    return {
        "opis": "Syntetyczne skany PDF; nie ocenia jakości LLM ani rachunków użytkowników",
        "python": platform.python_version(),
        "dpi": dpi, "wyniki": pomiary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="zapisz tylko metryki do JSON")
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--silniki", nargs="+", default=["pdfium", "poppler"],
                        choices=["pdfium", "poppler"])
    args = parser.parse_args(argv)
    raport = porownaj(tuple(args.silniki), args.dpi)
    for wynik in raport["wyniki"]:
        pola = wynik["zgodnosc_wartosci"]
        liczba = sum(pola.values())
        print(
            f"{wynik['przypadek']:13} {wynik['silnik']:7} "
            f"{wynik['czas_sekundy']:>7.3f} s  "
            f"tekst={wynik['podobienstwo_znakow']:.1%}  "
            f"wartosci={liczba}/3  metoda={wynik['metoda']}"
        )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(raport, ensure_ascii=False, indent=2)
                             + "\n", encoding="utf-8")
        print(f"Raport bez danych osobowych: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
