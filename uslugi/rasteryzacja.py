# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Dwie wymienne metody rasteryzacji PDF do lokalnego OCR.

PDFium jest domyślnym silnikiem produkcyjnym. Poppler pozostaje
opcjonalnym punktem odniesienia w porównaniu jakości OCR.
Ten moduł nie rozpoznaje żadnych pól rachunku.
"""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Literal

from PIL import Image

SilnikRasteryzacji = Literal["pdfium", "poppler"]

# PDFium NIE jest thread-safe, nawet dla różnych dokumentów.
# Wszelkie operacje pypdfium2 powinny korzystać z tej blokady.
_BLOKADA_PDFIUM = RLock()


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

    if silnik == "pdfium":
        # Bez mutexu równoległe zadania QRunnable/CLI mogą naruszyć pamięć.
        # Tworzenie, kopiowanie i zamknięcie obiektów PDFium są atomowe.
        with _BLOKADA_PDFIUM:
            import pypdfium2 as pdfium
            with pdfium.PdfDocument(str(plik)) as pdf:
                if numer_strony >= len(pdf):
                    raise ValueError(f"PDF nie ma strony {numer_strony + 1}")
                strona = pdf[numer_strony]
                try:
                    bitmapa = strona.render(
                        scale=dpi / 72.0, fill_color=(255, 255, 255, 255),
                    )
                    try:
                        obraz = bitmapa.to_pil().copy()
                    finally:
                        bitmapa.close()
                finally:
                    strona.close()
        # Obraz jest samodzielną kopią PIL; tutaj nie korzystamy z PDFium.
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
        last_page=numer_strony + 1, thread_count=1,
    )
    if len(obrazy) != 1:
        for obraz in obrazy:
            obraz.close()
        raise ValueError("Poppler nie wyrenderował wskazanej strony")
    return obrazy[0]
