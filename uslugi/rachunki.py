# SPDX-License-Identifier: GPL-3.0-only
"""Obsługa importu PDF i formularza rachunku (bez OCR)."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from baza.migracje import zastosuj_migracje
from baza.polaczenie import polacz, transakcja
from konfiguracja import katalog_danych
from uslugi.archiwum import MagazynDokumentow
from uslugi.walidacja import zweryfikuj_numer_konta


@dataclass(frozen=True)
class DaneRachunku:
    dokument_id: int
    dostawca: str
    numer: str
    kwota: str
    kategoria_id: int
    data_wystawienia: str = ""
    termin_platnosci: str = ""
    okres_od: str = ""
    okres_do: str = ""
    status: str = "do_zaplaty"
    uwagi: str = ""
    numer_konta: str = ""


def kwota_na_grosze(tekst: str) -> int:
    znormalizowana = tekst.strip().replace("\u00a0", "").replace(" ", "")
    if not re.fullmatch(r"\d{1,12}(?:[,.]\d{1,2})?", znormalizowana):
        raise ValueError("Kwota musi mieć postać np. 123,45 (maksymalnie 2 miejsca po przecinku)")
    return int(Decimal(znormalizowana.replace(",", ".")) * 100)


def grosze_na_kwote(grosze: int) -> str:
    return f"{grosze // 100},{grosze % 100:02d}"


def _data(tekst: str) -> str | None:
    tekst = tekst.strip()
    if not tekst:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", tekst):
        raise ValueError("Daty należy podawać w formacie RRRR-MM-DD")
    try:
        date.fromisoformat(tekst)
    except ValueError as blad:
        raise ValueError(f"Nieprawidłowa data: {tekst}") from blad
    return tekst


class RejestrRachunkow:
    def __init__(self, katalog: Path | None = None):
        self.katalog = Path(katalog if katalog is not None else katalog_danych()).resolve()
        self.katalog.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = polacz(self.katalog / "swistak.sqlite3")
        try:
            zastosuj_migracje(self.db)
            self.magazyn = MagazynDokumentow(self.katalog)
        except BaseException:
            self.db.close()
            raise

    def zamknij(self) -> None:
        self.db.close()

    def importuj_pdf(self, sciezka: str | Path) -> tuple[int, bool]:
        """Zwraca (id_dokumentu, czy_nowy); duplikaty rozpoznaje SHA-256."""
        plik = self.magazyn.kopiuj(sciezka)
        with transakcja(self.db):
            wiersz = self.db.execute(
                "SELECT id FROM dokumenty WHERE sha256 = ?", (plik.sha256,)
            ).fetchone()
            if wiersz:
                return int(wiersz["id"]), False
            kursor = self.db.execute(
                "INSERT INTO dokumenty "
                "(nazwa_zrodlowa, sha256, sciezka_wzgledna, rozmiar_bajtow) "
                "VALUES (?, ?, ?, ?)",
                (plik.nazwa_zrodlowa, plik.sha256, plik.sciezka_wzgledna, plik.rozmiar_bajtow),
            )
            return int(kursor.lastrowid), True

    def dokumenty(self) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "SELECT d.id, d.nazwa_zrodlowa, d.sha256, d.sciezka_wzgledna, "
            "d.dodano_utc, r.dostawca, r.kwota_grosze, r.status "
            "FROM dokumenty d LEFT JOIN rachunki r ON r.dokument_id = d.id "
            "ORDER BY d.id DESC"
        ))

    def dokument(self, dokument_id: int) -> sqlite3.Row:
        wiersz = self.db.execute("SELECT * FROM dokumenty WHERE id = ?", (dokument_id,)).fetchone()
        if wiersz is None:
            raise ValueError("Nie znaleziono dokumentu")
        return wiersz

    def sciezka_pdf(self, dokument_id: int) -> Path:
        wiersz = self.dokument(dokument_id)
        return self.magazyn.sciezka(wiersz["sciezka_wzgledna"], wiersz["sha256"])

    def kategorie(self) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "SELECT id, nazwa FROM kategorie WHERE aktywna = 1 ORDER BY nazwa COLLATE NOCASE"
        ))

    def dodaj_kategorie(self, nazwa: str) -> int:
        nazwa = " ".join(nazwa.split())
        if not (1 <= len(nazwa) <= 80):
            raise ValueError("Nazwa kategorii musi mieć od 1 do 80 znaków")
        try:
            with transakcja(self.db):
                kursor = self.db.execute("INSERT INTO kategorie(nazwa) VALUES (?)", (nazwa,))
                return int(kursor.lastrowid)
        except sqlite3.IntegrityError as blad:
            raise ValueError("Kategoria o tej nazwie już istnieje") from blad

    def rachunek(self, dokument_id: int) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT r.*, p.kategoria_id "
            "FROM rachunki r LEFT JOIN pozycje_rachunku p ON p.rachunek_id = r.id "
            "WHERE r.dokument_id = ? ORDER BY p.id LIMIT 1", (dokument_id,)
        ).fetchone()

    def zapisz_rachunek(self, dane: DaneRachunku) -> int:
        dostawca = " ".join(dane.dostawca.split())
        if not dostawca or len(dostawca) > 200:
            raise ValueError("Dostawca jest wymagany (maks. 200 znaków)")
        if len(dane.numer.strip()) > 120 or len(dane.uwagi) > 2000:
            raise ValueError("Za długi numer rachunku lub uwagi")
        if dane.status not in ("do_zaplaty", "oplacony"):
            raise ValueError("Nieprawidłowy status rachunku")
        numer_konta = zweryfikuj_numer_konta(dane.numer_konta)
        kwota = kwota_na_grosze(dane.kwota)
        wystawiono = _data(dane.data_wystawienia)
        termin = _data(dane.termin_platnosci)
        od = _data(dane.okres_od)
        do = _data(dane.okres_do)
        if od and do and od > do:
            raise ValueError("Początek okresu nie może być późniejszy niż koniec")
        with transakcja(self.db):
            if not self.db.execute("SELECT 1 FROM dokumenty WHERE id = ?", (dane.dokument_id,)).fetchone():
                raise ValueError("Nie znaleziono dokumentu")
            if not self.db.execute(
                "SELECT 1 FROM kategorie WHERE id = ? AND aktywna = 1", (dane.kategoria_id,)
            ).fetchone():
                raise ValueError("Wybierz istniejącą kategorię")
            istnieje = self.db.execute(
                "SELECT id FROM rachunki WHERE dokument_id = ?", (dane.dokument_id,)
            ).fetchone()
            wartosci = (dostawca, dane.numer.strip(), wystawiono, termin, od, do,
                       kwota, dane.status, dane.uwagi.strip(), numer_konta)
            if istnieje:
                rachunek_id = int(istnieje["id"])
                self.db.execute(
                    "UPDATE rachunki SET dostawca=?, numer=?, data_wystawienia=?, "
                    "termin_platnosci=?, okres_od=?, okres_do=?, kwota_grosze=?, "
                    "status=?, uwagi=?, numer_konta=?, zmieniono_utc=strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
                    "WHERE id=?", (*wartosci, rachunek_id)
                )
                self.db.execute("DELETE FROM pozycje_rachunku WHERE rachunek_id = ?", (rachunek_id,))
            else:
                kursor = self.db.execute(
                    "INSERT INTO rachunki (dokument_id, dostawca, numer, data_wystawienia, "
                    "termin_platnosci, okres_od, okres_do, kwota_grosze, status, uwagi, numer_konta) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (dane.dokument_id, *wartosci),
                )
                rachunek_id = int(kursor.lastrowid)
            # Etap 1: jedna pozycja obejmuje całą kwotę. Późniejszy podział na wiele
            # kategorii będzie wymagał osobnego edytora i weryfikacji sumy pozycji.
            self.db.execute(
                "INSERT INTO pozycje_rachunku(rachunek_id, kategoria_id, kwota_grosze) "
                "VALUES (?, ?, ?)", (rachunek_id, dane.kategoria_id, kwota),
            )
        return rachunek_id
