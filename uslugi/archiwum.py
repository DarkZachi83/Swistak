# SPDX-License-Identifier: GPL-3.0-only
"""Nienaruszalny magazyn PDF: SHA-256, atomowe przeniesienie i bez deduplikatów."""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class BladArchiwum(ValueError):
    pass


@dataclass(frozen=True)
class PlikArchiwalny:
    sha256: str
    sciezka_wzgledna: str
    rozmiar_bajtow: int
    nazwa_zrodlowa: str


def suma_pliku(sciezka: Path) -> str:
    hasz = hashlib.sha256()
    with open(sciezka, "rb") as plik:
        for blok in iter(lambda: plik.read(1024 * 1024), b""):
            hasz.update(blok)
    return hasz.hexdigest()


class MagazynDokumentow:
    def __init__(self, katalog_danych: Path):
        self.katalog_danych = Path(katalog_danych).resolve()
        self.katalog = self.katalog_danych / "dokumenty"
        self.katalog.mkdir(parents=True, exist_ok=True, mode=0o700)

    def kopiuj(self, zrodlo: str | Path) -> PlikArchiwalny:
        """Kopiuj plik, nie dotykając źródła.

        Plik tymczasowy powstaje w magazynie. Osobna nazwa według SHA-256
        sprawia, że powtórny import tego samego PDF nie tworzy drugiej kopii.
        Po awarii zapisu DB może pozostać bezpieczny, niepowiązany oryginał.
        """
        zrodlo = Path(zrodlo).expanduser()
        if not zrodlo.is_file() or zrodlo.suffix.lower() != ".pdf":
            raise BladArchiwum("Wskaż istniejący plik PDF")
        with zrodlo.open("rb") as sprawdz:
            if not sprawdz.read(1024).lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"%PDF-"):
                raise BladArchiwum("Plik nie ma nagłówka PDF")
        uchwyt, tymczasowa = tempfile.mkstemp(prefix=".import-", suffix=".tmp", dir=self.katalog)
        temp = Path(tymczasowa)
        hasz = hashlib.sha256()
        rozmiar = 0
        try:
            with os.fdopen(uchwyt, "wb") as cel, zrodlo.open("rb") as plik:
                for blok in iter(lambda: plik.read(1024 * 1024), b""):
                    cel.write(blok)
                    hasz.update(blok)
                    rozmiar += len(blok)
                cel.flush()
                os.fsync(cel.fileno())
            if rozmiar == 0:
                raise BladArchiwum("Pusty plik PDF")
            skrot = hasz.hexdigest()
            wzgledna = Path("dokumenty") / skrot[:2] / (skrot + ".pdf")
            cel = self.katalog_danych / wzgledna
            cel.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                # Hard link: pliku o tej nazwie nie nadpisujemy nawet przy
                # równoczesnych importach; wymagana wspólna partycja (ten sam folder).
                os.link(temp, cel)
            except FileExistsError:
                if not cel.is_file() or suma_pliku(cel) != skrot:
                    raise BladArchiwum("Archiwalny PDF nie zgadza się z sumą SHA-256")
            return PlikArchiwalny(skrot, wzgledna.as_posix(), rozmiar, zrodlo.name)
        finally:
            temp.unlink(missing_ok=True)

    def sciezka(self, wzgledna: str, oczekiwany_sha256: str | None = None) -> Path:
        kandydat = Path(wzgledna)
        if kandydat.is_absolute() or ".." in kandydat.parts:
            raise BladArchiwum("Niebezpieczna ścieżka dokumentu")
        cel = (self.katalog_danych / kandydat).resolve()
        if not cel.is_relative_to(self.katalog.resolve()):
            raise BladArchiwum("Ścieżka poza archiwum dokumentów")
        if not cel.is_file():
            raise BladArchiwum("Brak archiwalnego pliku PDF")
        if oczekiwany_sha256 and suma_pliku(cel) != oczekiwany_sha256:
            raise BladArchiwum("Archiwalny PDF został zmieniony lub uszkodzony")
        return cel
