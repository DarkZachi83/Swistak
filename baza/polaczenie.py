# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Połączenie SQLite z kluczami obcymi i jawnymi transakcjami."""
from __future__ import annotations

import errno
import logging
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator


def _ogranicz_uprawnienia(sciezka: Path, tryb: int) -> None:
    obecne = sciezka.stat()
    if stat.S_IMODE(obecne.st_mode) == tryb:
        return
    try:
        sciezka.chmod(tryb)
    except OSError as blad:
        if (blad.errno not in (errno.EACCES, errno.EPERM, errno.ENOSYS, errno.ENOTSUP)
                or obecne.st_uid != os.geteuid()):
            raise
    # FAT/exFAT mogą ignorować chmod albo odmówić go właścicielowi.
    # Wtedy rzeczywiste uprawnienia wynikają z opcji montowania.
    if stat.S_IMODE(sciezka.stat().st_mode) != tryb:
        logging.getLogger(__name__).warning(
            "Nie udało się ustawić uprawnień %04o dla %s. Sprawdź opcje montowania.",
            tryb, sciezka,
        )


def polacz(sciezka: Path) -> sqlite3.Connection:
    sciezka = Path(sciezka)
    sciezka.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        _ogranicz_uprawnienia(sciezka.parent, 0o700)
        if sciezka.is_symlink():
            raise OSError("Plik SQLite nie może być dowiązaniem symbolicznym")
        try:
            fd = os.open(sciezka, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        _ogranicz_uprawnienia(sciezka, 0o600)

    db = sqlite3.connect(sciezka, timeout=10, isolation_level=None)
    try:
        db.execute("PRAGMA trusted_schema = OFF")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        db.execute("PRAGMA synchronous = FULL")
        # Prosty plik bazy ułatwia późniejsze spójne kopie przy użyciu backup API.
        db.execute("PRAGMA journal_mode = DELETE")
        return db
    except BaseException:
        db.close()
        raise


def polacz_tylko_odczyt(sciezka: Path) -> sqlite3.Connection:
    uri = Path(sciezka).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
    try:
        db.execute("PRAGMA trusted_schema = OFF")
        db.execute("PRAGMA query_only = ON")
        db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = sqlite3.Row
        return db
    except BaseException:
        db.close()
        raise


@contextmanager
def transakcja(db: sqlite3.Connection) -> Iterator[None]:
    if db.in_transaction:
        raise RuntimeError("Nie można zagnieżdżać transakcji SQLite")
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
