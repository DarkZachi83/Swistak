# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Lokalne obrazy stron PDF dla multimodalnej analizy faktury.

Obrazów nie zapisujemy do archiwum ani na dysk; trafiają tylko do
lokalnej Ollamy. Ograniczenia chronią RAM i zapobiegają cichej utracie stron.
"""
from __future__ import annotations

import base64
import io
import threading
from pathlib import Path

from PIL import Image

from ai_core.errors import TaskCancelled
from uslugi.rasteryzacja import _BLOKADA_PDFIUM, rasteryzuj_strone

MAKS_STRON_WIZJI = 6
MAKS_BOK_OBRAZU = 1600
MAKS_BAJTOW_OBRAZU = 2_000_000
MAKS_BAJTOW_CALOSCI = 9_000_000


def przygotuj_obrazy_faktury(
    sciezka: str | Path, *, przerwij: threading.Event | None = None,
) -> list[str]:
    """Zakoduj WSZYSTKIE strony PDF albo zgłoś jawny błąd limitu."""
    plik = Path(sciezka).expanduser()
    if not plik.is_file() or plik.suffix.casefold() != ".pdf":
        raise ValueError("Nie znaleziono oryginalnego dokumentu PDF")
    import pypdfium2 as pdfium

    with _BLOKADA_PDFIUM:
        with pdfium.PdfDocument(str(plik)) as dokument:
            liczba = len(dokument)
    if not 1 <= liczba <= MAKS_STRON_WIZJI:
        raise ValueError(
            f"Analiza obrazu obsługuje od 1 do {MAKS_STRON_WIZJI} stron PDF; "
            f"dokument ma {liczba} stron. Nie pominięto żadnej strony po cichu."
        )

    obrazy: list[str] = []
    razem = 0
    for numer in range(liczba):
        if przerwij is not None and przerwij.is_set():
            raise TaskCancelled("Anulowano analizę obrazu")
        with rasteryzuj_strone(plik, numer, dpi=150) as oryginal:
            obraz = oryginal.copy()
            try:
                obraz.thumbnail(
                    (MAKS_BOK_OBRAZU, MAKS_BOK_OBRAZU),
                    Image.Resampling.LANCZOS,
                )
                bufor = io.BytesIO()
                obraz.save(bufor, format="JPEG", quality=80)
                dane = bufor.getvalue()
                if len(dane) > MAKS_BAJTOW_OBRAZU:
                    bufor = io.BytesIO()
                    obraz.save(bufor, format="JPEG", quality=60)
                    dane = bufor.getvalue()
            finally:
                obraz.close()
        razem += len(dane)
        if len(dane) > MAKS_BAJTOW_OBRAZU or razem > MAKS_BAJTOW_CALOSCI:
            raise ValueError("Obrazy faktury są zbyt duże do bezpiecznej analizy AI")
        obrazy.append(base64.b64encode(dane).decode("ascii"))
    if przerwij is not None and przerwij.is_set():
        raise TaskCancelled("Anulowano analizę obrazu")
    return obrazy
