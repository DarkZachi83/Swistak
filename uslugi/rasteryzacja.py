# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Dwie wymienne metody rasteryzacji PDF do lokalnego OCR.

PDFium jest domyślnym silnikiem produkcyjnym. Poppler pozostaje
opcjonalnym punktem odniesienia w porównaniu jakości OCR.
Ten moduł nie rozpoznaje żadnych pól rachunku.
"""
from __future__ import annotations

from math import ceil, isfinite, sqrt
from pathlib import Path
from threading import RLock
from typing import Literal

from PIL import Image

SilnikRasteryzacji = Literal["pdfium", "poppler"]

MAKS_PIKSELI_STRONY = 16_000_000
MAKS_BOK_STRONY = 8192

# PDFium NIE jest thread-safe, nawet dla różnych dokumentów.
# Wszelkie operacje pypdfium2 powinny korzystać z tej blokady.
_BLOKADA_PDFIUM = RLock()


def _skala_i_rozmiar(szer: float, wys: float, dpi: int) -> tuple[float, tuple[int, int]]:
    if not (isfinite(szer) and isfinite(wys) and szer > 0 and wys > 0):
        raise ValueError("PDF ma nieprawidłowy rozmiar strony")
    zadana_skala = dpi / 72.0
    w, h = ceil(szer * zadana_skala), ceil(wys * zadana_skala)
    if max(w, h) <= MAKS_BOK_STRONY and w * h <= MAKS_PIKSELI_STRONY:
        return zadana_skala, (w, h)
    # PDFium zaokrągla oba wymiary w górę. Rezerwa na dwa brzegi
    # utrzymuje pole bitmapy poniżej limitu również po ceil().
    pole = MAKS_PIKSELI_STRONY - 2 * MAKS_BOK_STRONY
    skala = min((MAKS_BOK_STRONY - 1) / max(szer, wys), sqrt(pole / szer / wys))
    return skala, (ceil(szer * skala), ceil(wys * skala))


def rasteryzuj_strone(
    sciezka: str | Path, numer_strony: int, dpi: int = 220,
    silnik: SilnikRasteryzacji = "pdfium",
) -> Image.Image:
    """Zwróć niezależny obraz PIL RGB bez trzymania otwartego dokumentu.

    Indeksy stron liczone od zera, tak samo jak w QPdfDocument/pdfplumber.
    Wywołujący jest właścicielem obrazu i powinien wywołać .close().
    """
    if silnik not in ("pdfium", "poppler"):
        raise ValueError("Nieznany silnik rasteryzacji; wybierz pdfium albo poppler")
    if numer_strony < 0:
        raise ValueError("Numer strony nie może być ujemny")
    if not 100 <= dpi <= 400:
        raise ValueError("DPI rasteryzacji musi być w zakresie 100–400")
    plik = Path(sciezka).expanduser()
    if not plik.is_file():
        raise FileNotFoundError(f"Nie znaleziono PDF: {plik}")

    # Oba silniki potrzebują bezpiecznych wymiarów przed alokacją bitmapy.
    with _BLOKADA_PDFIUM:
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(str(plik)) as pdf:
            if numer_strony >= len(pdf):
                raise ValueError(f"PDF nie ma strony {numer_strony + 1}")
            strona = pdf[numer_strony]
            try:
                skala, rozmiar = _skala_i_rozmiar(*strona.get_size(), dpi)
                if silnik == "pdfium":
                    bitmapa = strona.render(
                        scale=skala, fill_color=(255, 255, 255, 255),
                    )
                    try:
                        obraz = bitmapa.to_pil().copy()
                    finally:
                        bitmapa.close()
                elif strona.get_rotation() in (90, 270):
                    # pdftoppm przyjmuje wymiary przed obrotem strony.
                    rozmiar = (rozmiar[1], rozmiar[0])
            finally:
                strona.close()

    if silnik == "pdfium":
        if obraz.mode != "RGB":
            rgb = obraz.convert("RGB")
            obraz.close()
            obraz = rgb
        return obraz

    # Poppler: tylko do eksperymentów porównawczych. pdf2image i binaria
    # Popplera NIE są wymagane przy zwykłym uruchomieniu Świstaka.
    try:
        from pdf2image import convert_from_path
    except ImportError as blad:
        raise RuntimeError(
            "Opcjonalne porównanie z Popplerem wymaga: "
            "pip install -r requirements-compare.txt"
        ) from blad
    obrazy = convert_from_path(
        str(plik), dpi=dpi, first_page=numer_strony + 1,
        last_page=numer_strony + 1, thread_count=1, use_cropbox=True, size=rozmiar,
    )
    if len(obrazy) != 1:
        for obraz in obrazy:
            obraz.close()
        raise ValueError("Poppler nie wyrenderował wskazanej strony")
    return obrazy[0]
