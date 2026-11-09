# SPDX-License-Identifier: GPL-3.0-only
"""Połączenie SQLite z kluczami obcymi i jawnymi transakcjami."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator


def polacz(sciezka: Path) -> sqlite3.Connection:
    sciezka = Path(sciezka)
    sciezka.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(sciezka, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 10000")
    db.execute("PRAGMA synchronous = FULL")
    # Prosty plik bazy ułatwia późniejsze spójne kopie przy użyciu backup API.
    db.execute("PRAGMA journal_mode = DELETE")
    return db


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
