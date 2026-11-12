# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Lokalny odczyt QR z PDF bez OCR, chmury, bankowości i zapisu do bazy."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from uslugi.rasteryzacja import rasteryzuj_strone
from uslugi.walidacja import poprawny_iban


class BladOdczytuQR(RuntimeError):
    """Brak dekodera QR lub problem z PDF."""


class OdczytQRAnulowany(BladOdczytuQR):
    """Przerwanie skanowania QR przez użytkownika."""


@dataclass(frozen=True)
class PlatnoscQR:
    nip: str
    kraj: str
    numer_konta: str
    kwota_grosze: int
    odbiorca: str
    tytul: str


@dataclass(frozen=True)
class KodQR:
    strona: int  # 0-based
    tresc: str
    platnosc: PlatnoscQR | None


def rozpoznaj_platnosc(tresc: str) -> PlatnoscQR | None:
    """Rozpoznaj tylko znany format: NIP|PL|NRB|grosze|odbiorca|tytul|....

    Inne QR są zachowane jako surowy tekst, bez zgadywania pól.
    """
    pola = tresc.strip().split("|")
    if len(pola) < 6:
        return None
    nip, kraj, konto, grosze, odbiorca, tytul = (s.strip() for s in pola[:6])
    if (kraj != "PL" or not re.fullmatch(r"\d{10}", nip)
            or not re.fullmatch(r"\d{26}", konto)
            or not poprawny_iban(konto)
            or not re.fullmatch(r"\d{1,12}", grosze)
            or not odbiorca or len(odbiorca) > 200
            or len(tytul) > 250):
        return None
    return PlatnoscQR(nip, kraj, konto, int(grosze), odbiorca, tytul)


def odczytaj_kody_qr(
    sciezka: str | Path, *, dpi: int = 250, maks_stron: int = 30,
    przerwij: threading.Event | None = None,
) -> tuple[KodQR, ...]:
    """Odczytaj kody QR z obrazów stron PDF przez PDFium (wspólna blokada OCR)."""
    if not 100 <= dpi <= 400 or not 1 <= maks_stron <= 100:
        raise ValueError("Niepoprawne parametry odczytu QR")
    pdf = Path(sciezka).expanduser()
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise BladOdczytuQR("Nie znaleziono dokumentu PDF")
    try:
        import zxingcpp
    except ImportError as exc:
        raise BladOdczytuQR(
            "Brak dekodera QR; zainstaluj zależności z requirements.txt"
        ) from exc
    if przerwij is not None and przerwij.is_set():
        raise OdczytQRAnulowany("Odczyt QR anulowano")
    try:
        with pdfplumber.open(pdf) as dokument:
            liczba = len(dokument.pages)
        if not 1 <= liczba <= maks_stron:
            raise BladOdczytuQR(
                f"PDF zawiera {liczba} stron; limit odczytu QR to {maks_stron}"
            )
        kody: list[KodQR] = []
        for numer in range(liczba):
            if przerwij is not None and przerwij.is_set():
                raise OdczytQRAnulowany("Odczyt QR anulowano")
            with rasteryzuj_strone(pdf, numer, dpi) as obraz:
                wyniki = zxingcpp.read_barcodes(obraz)
            for wynik in wyniki:
                if wynik.format != zxingcpp.BarcodeFormat.QRCode:
                    continue
                tekst = str(wynik.text)
                if not tekst.strip() or len(tekst) > 2048:
                    continue
                kody.append(KodQR(numer, tekst, rozpoznaj_platnosc(tekst)))
                if len(kody) >= 30:
                    return tuple(kody)
        if przerwij is not None and przerwij.is_set():
            raise OdczytQRAnulowany("Odczyt QR anulowano")
        return tuple(kody)
    except (BladOdczytuQR, ValueError):
        raise
    except Exception as exc:
        raise BladOdczytuQR(f"Nie udało się odczytać QR: {exc}") from exc
