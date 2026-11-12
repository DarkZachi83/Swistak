# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Przygotowanie pustej bazy i ostrożne usunięcie prywatnych danych Świstaka.

Warstwa GUI wymaga uprzednio UTWORZONEGO i ZWERYFIKOWANEGO backupu ZIP
oraz jawnego, wieloetapowego potwierdzenia. Tutaj wykonuje się wyłącznie
bezpieczne podmienianie katalogów, bez ingerencji w kopię ZIP.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from uslugi.rachunki import RejestrRachunkow


class BladCzyszczenia(RuntimeError):
    pass


_DOZWOLONE = frozenset({
    "swistak.sqlite3", "dokumenty", "wzorce", "kopie_migracji",
})
_KATALOGI = frozenset({"dokumenty", "wzorce", "kopie_migracji"})


def _sprawdz_katalog(root: Path) -> None:
    """Nie czyść przypadkowego katalogu wskazanego przez SWISTAK_DATA_DIR."""
    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise BladCzyszczenia("Katalog danych nie istnieje lub jest dowiązaniem")
    if root == root.parent or root == Path.home().resolve():
        raise BladCzyszczenia("Odmowa czyszczenia katalogu systemowego lub domowego")
    if not (root / "swistak.sqlite3").is_file():
        raise BladCzyszczenia("Brak bazy Świstaka — nie wolno czyścić katalogu")
    for path in root.iterdir():
        if path.name not in _DOZWOLONE or path.is_symlink():
            raise BladCzyszczenia(
                "Katalog zawiera obce pliki lub dowiązania; "
                "czyszczenie zablokowane: " + path.name
            )
        if path.name in _KATALOGI and not path.is_dir():
            raise BladCzyszczenia("Nieprawidłowa struktura danych: " + path.name)


def przygotuj_pusta_baze(root: Path) -> Path:
    """Utwórz w sąsiednim katalogu pustą, poprawnie zmigrowaną bazę."""
    root = Path(root).absolute()
    _sprawdz_katalog(root)
    stage = Path(tempfile.mkdtemp(prefix=".swistak-wyczysc-", dir=root.parent))
    try:
        reg = RejestrRachunkow(stage)
        try:
            if reg.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise BladCzyszczenia("Nowa baza nie przeszła kontroli SQLite")
            if reg.db.execute("SELECT COUNT(*) FROM rachunki").fetchone()[0] != 0:
                raise BladCzyszczenia("Nowa baza nie jest pusta")
            if reg.db.execute("SELECT COUNT(*) FROM dokumenty").fetchone()[0] != 0:
                raise BladCzyszczenia("Nowe archiwum nie jest puste")
        finally:
            reg.zamknij()
        return stage
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def podmien_na_pusta(root: Path, stage: Path) -> Path:
    """Podmień katalog na przygotowany; cofaj pierwszy rename po błędzie."""
    root, stage = Path(root).absolute(), Path(stage).absolute()
    _sprawdz_katalog(root)
    if (stage.is_symlink() or not stage.is_dir()
            or stage.parent != root.parent
            or not stage.name.startswith(".swistak-wyczysc-")
            or not (stage / "swistak.sqlite3").is_file()):
        raise BladCzyszczenia("Niebezpieczny katalog przygotowanej bazy")
    previous = root.with_name(
        root.name + "-przed-wyczyszczeniem-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-" + uuid.uuid4().hex[:8]
    )
    os.replace(root, previous)
    try:
        os.replace(stage, root)
    except BaseException:
        os.replace(previous, root)
        raise
    return previous


def usun_poprzednie_dane(previous: Path, root: Path) -> None:
    """Usuń tylko znany katalog właśnie wycofany z aktywnej bazy.

    Nigdy nie dotykaj ZIP-a zapisanego poza katalogiem danych.
    """
    previous, root = Path(previous).absolute(), Path(root).absolute()
    if (previous.is_symlink() or not previous.is_dir()
            or previous.parent != root.parent
            or not previous.name.startswith(root.name + "-przed-wyczyszczeniem-")
            or not root.is_dir()):
        raise BladCzyszczenia("Niebezpieczna lokalizacja starej bazy")
    _sprawdz_katalog(previous)
    shutil.rmtree(previous)
