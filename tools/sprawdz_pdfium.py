# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Lokalny manifest plików licencyjnych pypdfium2/PDFium z zainstalowanego wheel.

Służy do weryfikacji konkretnego zestawu binarnego. NIE potwierdza
kompletności licencji ani zgodności z wymaganiami dystrybucyjnymi.
Wynik nie zawiera danych z dokumentów użytkownika.
"""
from __future__ import annotations

import argparse
import json
from importlib import metadata
from pathlib import Path


FRAZY_LICENCJI = ("license", "licence", "notice", "copying", "copyright", "reuse.toml")
FRAZY_BINARIUM = ("libpdfium", "pdfium.dll", "libgcc", "libstdc++")


def manifest_pdfium() -> dict:
    try:
        distro = metadata.distribution("pypdfium2")
    except metadata.PackageNotFoundError as blad:
        raise RuntimeError("Brak pypdfium2. Zainstaluj requirements.txt") from blad

    pliki = distro.files
    if pliki is None:
        return {
            "wersja_pypdfium2": distro.version,
            "dokumentacja": "Brak listy RECORD w metadanych instalacji",
            "pliki_licencji": [],
            "binaria": [],
            "ostrzezenia": ["Brak manifestu RECORD: konieczny ręczny audyt wheel"],
        }

    licencje = []
    binaria = []
    for plik in pliki:
        nazwa = plik.as_posix()
        lo = nazwa.lower()
        if any(f in lo for f in FRAZY_LICENCJI):
            licencje.append(nazwa)
        if any(f in lo for f in FRAZY_BINARIUM):
            binaria.append(nazwa)

    ostrzezenia = []
    if not any("pdfium" in p.lower() and "license" in p.lower()
               for p in licencje):
        ostrzezenia.append(
            "Nie potwierdzono kompletu licencji PDFium w RECORD; "
            "sprawdź ręcznie BUILD_LICENSES i zbudowane binaria"
        )
    if any("libgcc" in p.lower() for p in binaria):
        ostrzezenia.append("Występuje libgcc — zbadaj licencję runtime")
    return {
        "wersja_pypdfium2": distro.version,
        "pliki_licencji": sorted(licencje),
        "binaria": sorted(binaria),
        "ostrzezenia": ostrzezenia,
        "uwaga": "To wykaz nazw plików, nie kopie treści licencji ani opinia prawna",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Zapisz manifest bez danych rachunków")
    args = parser.parse_args()
    dane = manifest_pdfium()
    wynik = json.dumps(dane, indent=2, ensure_ascii=False)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(wynik + "\n", encoding="utf-8")
        print(f"Manifest pakietu PDFium: {args.json}")
    else:
        print(wynik)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
