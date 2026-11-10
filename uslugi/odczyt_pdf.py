# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Odczyt tekstu PDF / OCR skanów. Bez rozpoznawania pól rachunku.

LLM-first: ten moduł WYŁĄCZNIE pozyskuje tekst i przekazuje go później
do Ollamy. Nie dopasowuje kwot, terminów ani dostawców za pomocą reguł.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from uslugi.geometria import Zaznaczenie


class BladOdczytu(RuntimeError):
    """Odczyt nie może zostać wykonany lub brakuje silnika OCR."""


class OdczytAnulowany(BladOdczytu):
    """Użytkownik przerwał przetwarzanie."""


@dataclass(frozen=True)
class TekstStrony:
    strona: int  # 0-based
    tekst: str
    metoda: str  # 'tekst', 'ocr', 'brak'


@dataclass(frozen=True)
class WynikOdczytu:
    strony: tuple[TekstStrony, ...]

    @property
    def tekst_dla_llm(self) -> str:
        """Zachowaj numery stron i ich kolejność, nie wykonuj interpretacji."""
        return "\n\n".join(
            f"=== STRONA {s.strona + 1} (metoda: {s.metoda}) ===\n{s.tekst}"
            for s in self.strony if s.tekst.strip()
        )

    @property
    def czy_pusty(self) -> bool:
        return not any(s.tekst.strip() for s in self.strony)


def _sprawdz_anulowanie(przerwij: threading.Event | None) -> None:
    if przerwij is not None and przerwij.is_set():
        raise OdczytAnulowany("Odczyt anulowano")


def _bbox(page, region: Zaznaczenie) -> tuple[float, float, float, float]:
    if not (0 <= region.lewo < region.prawo <= 1 and
            0 <= region.gora < region.dol <= 1):
        raise ValueError("Niepoprawne współrzędne zaznaczenia PDF")
    # pdfplumber: x0, top, x1, bottom względem górnego lewego rogu strony.
    return (
        float(region.lewo * page.width),
        float(region.gora * page.height),
        float(region.prawo * page.width),
        float(region.dol * page.height),
    )


def _uruchom_ocr(sciezka: Path, numer_strony: int,
                  region: Zaznaczenie | None, dpi: int, jezyk: str) -> str:
    """Poppler → PIL → Tesseract. Jeden obraz na raz, bez zapisywania skanu."""
    try:
        from pdf2image import convert_from_path
        import pytesseract

        obrazy = convert_from_path(
            str(sciezka), dpi=dpi,
            first_page=numer_strony + 1, last_page=numer_strony + 1,
            thread_count=1,
        )
        if not obrazy:
            raise BladOdczytu(f"Nie udało się wyrenderować strony {numer_strony + 1}")
        with obrazy[0] as obraz:
            if region is not None:
                szer, wys = obraz.size
                ramka = (
                    round(region.lewo * szer), round(region.gora * wys),
                    round(region.prawo * szer), round(region.dol * wys),
                )
                if ramka[2] <= ramka[0] or ramka[3] <= ramka[1]:
                    raise BladOdczytu("Zaznaczony obszar ma zerowy rozmiar")
                obraz = obraz.crop(ramka)
            return pytesseract.image_to_string(
                obraz, lang=jezyk, config="--psm 6" if region else "--psm 3",
                timeout=90,
            ).strip()
    except OdczytAnulowany:
        raise
    except BladOdczytu:
        raise
    except Exception as blad:
        raise BladOdczytu(
            "OCR nie powiódł się. Sprawdź instalację Popplera, Tesseract "
            f"i polskich danych językowych (pol). Szczegóły: {blad}"
        ) from blad


def odczytaj_pdf(
    sciezka: str | Path,
    obszar: Zaznaczenie | None = None,
    *,
    z_ocr: bool = True,
    dpi: int = 220,
    jezyk: str = "pol+eng",
    przerwij: threading.Event | None = None,
    maks_stron: int = 50,
) -> WynikOdczytu:
    """Pozyskaj tekst z warstwy PDF, a dla stron bez tekstu uruchom OCR.

    OCR jest fallbackiem *technicznym* dla brakującej warstwy tekstowej,
    NIE fallbackiem rozpoznawania informacji, za które odpowiada LLM.
    Zaznaczenie dotyczy jednej strony i jest niezależne od zoomu GUI.
    """
    plik = Path(sciezka).expanduser()
    if not plik.is_file() or plik.suffix.lower() != ".pdf":
        raise BladOdczytu("Nie znaleziono pliku PDF")
    if not (100 <= dpi <= 400):
        raise ValueError("DPI OCR musi być w zakresie 100–400")
    if maks_stron < 1:
        raise ValueError("Limit stron musi być dodatni")
    _sprawdz_anulowanie(przerwij)
    wynik: list[TekstStrony] = []
    try:
        with pdfplumber.open(plik) as pdf:
            liczba = len(pdf.pages)
            if liczba == 0:
                raise BladOdczytu("Dokument PDF nie ma stron")
            if liczba > maks_stron and obszar is None:
                raise BladOdczytu(
                    f"Dokument ma {liczba} stron; limit automatycznego odczytu to "
                    f"{maks_stron}. Zaznacz pojedynczy obszar."
                )
            if obszar is not None and not (0 <= obszar.strona < liczba):
                raise BladOdczytu("Wybrana strona nie istnieje w PDF")

            indeksy = [obszar.strona] if obszar else range(liczba)
            for numer in indeksy:
                _sprawdz_anulowanie(przerwij)
                strona = pdf.pages[numer]
                fragment = strona.crop(_bbox(strona, obszar)) if obszar else strona
                try:
                    tekst = (fragment.extract_text() or "").strip()
                except Exception as blad:
                    raise BladOdczytu(
                        f"Nie udało się przeczytać warstwy tekstowej strony {numer + 1}"
                    ) from blad
                # Nieliczne znaki mogą pochodzić np. ze stopki zeskanowanej strony.
                prog = 4 if obszar else 15
                metoda = "tekst" if len(tekst) >= prog else "brak"
                if metoda == "brak" and z_ocr:
                    _sprawdz_anulowanie(przerwij)
                    tekst_ocr = _uruchom_ocr(plik, numer, obszar, dpi, jezyk)
                    _sprawdz_anulowanie(przerwij)
                    if tekst_ocr:
                        tekst, metoda = tekst_ocr, "ocr"
                elif metoda == "brak" and tekst:
                    metoda = "tekst"  # zachowaj krótki odczyt przy wyłączonym OCR
                wynik.append(TekstStrony(numer, tekst, metoda))
                strona.flush_cache()
                _sprawdz_anulowanie(przerwij)
    except (BladOdczytu, ValueError):
        raise
    except Exception as blad:
        raise BladOdczytu(f"Nie można odczytać dokumentu PDF: {blad}") from blad
    return WynikOdczytu(tuple(wynik))
