# SPDX-License-Identifier: GPL-3.0-only
"""Wersjonowane migracje .sql z kontrolą niezmienności plików."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from baza.polaczenie import transakcja


class BladMigracji(RuntimeError):
    """Niezgodność bazy lub migracji ze schematem programu."""


def _polecenia(sql: str):
    """Wykonuj polecenia osobno, nie używając executescript (łamie transakcję)."""
    bufor = ""
    for linia in sql.splitlines(keepends=True):
        bufor += linia
        if sqlite3.complete_statement(bufor):
            if bufor.strip():
                yield bufor
            bufor = ""
    if bufor.strip():
        raise BladMigracji("Migracja zawiera niekompletne polecenie SQL")


def zastosuj_migracje(db: sqlite3.Connection, katalog: Path | None = None) -> None:
    katalog = katalog or (Path(__file__).parent / "schemat")
    pliki = sorted(katalog.glob("[0-9][0-9][0-9]_*.sql"))
    if not pliki:
        raise BladMigracji("Brak plików migracji bazy")
    with transakcja(db):
        db.execute(
            "CREATE TABLE IF NOT EXISTS migracje ("
            "nazwa TEXT PRIMARY KEY, sha256 TEXT NOT NULL, "
            "wdrozono_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))"
        )
        zapisane = {wiersz["nazwa"]: wiersz["sha256"]
                    for wiersz in db.execute("SELECT nazwa, sha256 FROM migracje")}
        nazwy = {plik.name for plik in pliki}
        nadmiar = set(zapisane) - nazwy
        if nadmiar:
            raise BladMigracji("Baza pochodzi z nowszej wersji programu: " + ", ".join(sorted(nadmiar)))
        for plik in pliki:
            tresc = plik.read_bytes()
            sha = hashlib.sha256(tresc).hexdigest()
            if plik.name in zapisane:
                if zapisane[plik.name] != sha:
                    raise BladMigracji(f"Zmieniono wcześniej zastosowaną migrację: {plik.name}")
                continue
            try:
                sql = tresc.decode("utf-8-sig")
                for polecenie in _polecenia(sql):
                    db.execute(polecenie)
                db.execute("INSERT INTO migracje (nazwa, sha256) VALUES (?, ?)", (plik.name, sha))
            except (sqlite3.Error, UnicodeError) as blad:
                raise BladMigracji(f"Nie udało się zastosować {plik.name}: {blad}") from blad
