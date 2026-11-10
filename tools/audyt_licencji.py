# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Wstępny audyt licencji i zakresu zależności Świstaka.

Używa wyłącznie standardowej biblioteki Pythona; nie łączy się z siecią,
nie bada dokumentów użytkownika i nie wydaje oceny zgodności prawnej.

Uruchom:
  python -m tools.audyt_licencji
  python -m tools.audyt_licencji --check

Dla konkretnego instalatora potrzebny jest dodatkowo prawdziwy SBOM
i kopie wszystkich wymaganych tekstów licencji z zapakowanych bibliotek.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from importlib import metadata
from pathlib import Path


KATALOG = Path(__file__).resolve().parents[1]
DOZWOLONE_STATUSY = {"review", "high-risk", "notice", "separate-terms"}
DOZWOLONE_RODZAJE = {
    "python-direct", "python-transitive", "python-transitive-optional",
    "system", "external", "model",
}


def wymagane_pakiety(tresc: str) -> set[str]:
    """Pobierz nazwy bezpośrednich zależności z prostego requirements.txt.

    Niezrozumiała składnia (np. URL, -r, git+) skutkuje błędem audytu:
    nie pozwalamy po cichu pominąć nowych zależności.
    """
    wynik: set[str] = set()
    for numer, surowy in enumerate(tresc.splitlines(), 1):
        tekst = surowy.split("#", 1)[0].strip()
        if not tekst:
            continue
        if tekst.startswith(("-", "git+", "https:", "http:")):
            raise ValueError(f"Nieobsługiwana deklaracja w requirements.txt:{numer}: {tekst}")
        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[A-Za-z0-9_.,-]+\])?"
            r"(?:[<>=!~].+)?", tekst
        )
        if not match:
            raise ValueError(f"Nierozpoznana zależność w requirements.txt:{numer}: {tekst}")
        wynik.add(match.group(1).lower().replace("_", "-").replace(".", "-"))
    return wynik


def sprawdz_rejestr(rejestr: dict, wymagane: set[str]) -> list[str]:
    bledy: list[str] = []
    if rejestr.get("schema_version") != 1:
        bledy.append("Nieobsługiwana wersja schematu rejestru")
    wiersze = rejestr.get("components")
    if not isinstance(wiersze, list):
        return ["Niepoprawny format components"]
    nazwy: set[str] = set()
    bezposrednie: set[str] = set()
    for komponent in wiersze:
        if not isinstance(komponent, dict):
            bledy.append("W rejestrze znajduje się niepoprawny wpis")
            continue
        nazwa = komponent.get("name", "")
        znormalizowana = nazwa.lower().replace("_", "-").replace(".", "-")
        if not nazwa or znormalizowana in nazwy:
            bledy.append(f"Brak nazwy lub duplikat: {nazwa!r}")
        nazwy.add(znormalizowana)
        if komponent.get("kind") not in DOZWOLONE_RODZAJE:
            bledy.append(f"Niepoprawny rodzaj: {nazwa}")
        if komponent.get("status") not in DOZWOLONE_STATUSY:
            bledy.append(f"Niepoprawny status: {nazwa}")
        if not all(isinstance(komponent.get(k), str) and komponent[k].strip()
                   for k in ("license", "source_url", "purpose")):
            bledy.append(f"Brak deklaracji licencji, źródła lub celu: {nazwa}")
        if komponent.get("kind") == "python-direct":
            bezposrednie.add(znormalizowana)
    for nazwa in sorted(wymagane - bezposrednie):
        bledy.append(f"Brak bezpośredniej zależności w rejestrze: {nazwa}")
    for nazwa in sorted(bezposrednie - wymagane):
        bledy.append(f"Usunięta z requirements.txt, nadal deklarowana jako bezpośrednia: {nazwa}")
    return bledy


def metadane_pakietu(nazwa: str) -> tuple[str, str]:
    try:
        paczka = metadata.distribution(nazwa)
    except metadata.PackageNotFoundError:
        return "BRAK", "Brak w tym środowisku"
    dane = paczka.metadata
    licencja = dane.get("License-Expression") or dane.get("License")
    if not licencja:
        licencje = [x for x in (dane.get_all("Classifier") or [])
                    if x.startswith("License ::")]
        licencja = "; ".join(licencje) or "Nieustalone z metadanych"
    return paczka.version, " ".join(str(licencja).split())[:100]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Świstak — audyt rejestru zależności")
    parser.add_argument("--check", action="store_true",
                        help="niezerowy kod wyjścia gdy bezpośrednie zależności nie są opisane lub nie są zainstalowane")
    args = parser.parse_args(argv)
    rejestr = json.loads((KATALOG / "licencje" / "rejestr.json").read_text("utf-8"))
    wymagane = wymagane_pakiety((KATALOG / "requirements.txt").read_text("utf-8"))
    bledy = sprawdz_rejestr(rejestr, wymagane)
    print("ŚWISTAK — WSTĘPNY REJESTR ZALEŻNOŚCI")
    print("Uwaga: metadane pakietów nie zastępują audytu prawnego pakietu!")
    print("Pakiet | Wersja w środowisku | Licencja w metadanych")
    print("-" * 85)
    for c in rejestr["components"]:
        if not c["kind"].startswith("python-"):
            continue
        wersja, licencja = metadane_pakietu(c["name"])
        print(f"{c['name']} | {wersja} | {licencja}")
        if args.check and c["kind"] == "python-direct" and wersja == "BRAK":
            bledy.append(f"Brak zainstalowanego pakietu: {c['name']}")
    print("\nZidentyfikowane zagadnienia do przeglądu:")
    for c in rejestr["components"]:
        if c["status"] in ("high-risk", "separate-terms", "review"):
            print(f" - {c['name']}: {c['status']} ({c['purpose']})")
    if bledy:
        for blad in bledy:
            print(f"BŁĄD REJESTRU: {blad}", file=sys.stderr)
        return 1
    print("\nRejestr bezpośrednich zależności spójny. "
          "To NIE jest zatwierdzenie dystrybucji komercyjnej.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
