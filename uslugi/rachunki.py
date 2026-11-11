# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Obsługa importu PDF i formularza rachunku (bez OCR)."""
from __future__ import annotations

import re
import sqlite3
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
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


class FakturaJuzIstnieje(ValueError):
    """Zapis wymaga osobnej zgody na nadpisanie już istniejącej faktury."""

    def __init__(self, rachunek_id: int):
        self.rachunek_id = rachunek_id
        super().__init__("Faktura jest już w bazie — wymagane potwierdzenie nadpisania")


def _klucz_faktury(wartosc: str) -> str:
    """Ujednolica spacje i wielkość liter bez modyfikowania numeru w SQLite."""
    return " ".join(wartosc.split()).casefold()


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
        sciezka_bazy = self.katalog / "swistak.sqlite3"
        byla_baza = sciezka_bazy.is_file() and sciezka_bazy.stat().st_size > 0
        self.db = polacz(sciezka_bazy)
        try:
            # Przed zmianą istniejącego schematu twórz snapshot samej bazy.
            # Pełny backup (baza + PDF-y) pozostaje oddzielnym etapem.
            if byla_baza and self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='migracje'"
            ).fetchone() and not self.db.execute(
                "SELECT 1 FROM migracje WHERE nazwa='002_numer_konta.sql'"
            ).fetchone():
                self._kopia_bazy_przed_migracja()
            zastosuj_migracje(self.db)
            self.magazyn = MagazynDokumentow(self.katalog)
        except BaseException:
            self.db.close()
            raise

    def _kopia_bazy_przed_migracja(self) -> Path:
        """Spójna kopia SQLite sprzed migracji, zapisana atomowo.

        Nie obejmuje plików PDF: do pełnego backupu potrzebny będzie etap 4.
        Nie pomijaj błędu wykonania kopii przed zmianą schematu.
        """
        katalog = self.katalog / "kopie_migracji"
        katalog.mkdir(parents=True, exist_ok=True, mode=0o700)
        nazwa = (
            "swistak-przed-migracja-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-" + uuid.uuid4().hex[:8] + ".sqlite3"
        )
        cel = katalog / nazwa
        deskryptor, tmp = tempfile.mkstemp(prefix=".przygotuj-", suffix=".tmp", dir=katalog)
        os.close(deskryptor)
        try:
            kopia = sqlite3.connect(tmp)
            try:
                self.db.backup(kopia)
            finally:
                kopia.close()
            os.replace(tmp, cel)
            os.chmod(cel, 0o600)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return cel

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

    def faktury(self) -> list[sqlite3.Row]:
        """Zapisane faktury wraz z PDF i kategorią, wyłącznie odczyt SQLite.

        W obecnej wersji każda faktura ma jedną pozycję. Kategorię czytamy
        osobnym podzapytaniem, aby jeden rachunek zawsze dawał jeden wiersz.
        Nie obejmuje dokumentów PDF, dla których nie zapisano faktury.
        """
        return list(self.db.execute(
            "SELECT r.id, r.dokument_id, r.dostawca, r.numer, "
            "r.data_wystawienia, r.termin_platnosci, r.kwota_grosze, r.status, "
            "d.nazwa_zrodlowa, "
            "COALESCE((SELECT k.nazwa FROM pozycje_rachunku p "
            "JOIN kategorie k ON k.id = p.kategoria_id "
            "WHERE p.rachunek_id = r.id ORDER BY p.id LIMIT 1), '') AS kategoria "
            "FROM rachunki r "
            "JOIN dokumenty d ON d.id = r.dokument_id "
            "ORDER BY r.id DESC"
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

    def _pasujace_faktury(self, dane: DaneRachunku) -> list[sqlite3.Row]:
        """Rozpoznaje ten sam PDF lub dostawcę + numer faktury.

        Sam dostawca bez numeru nie wystarcza — miesięczne faktury tego
        samego operatora nie mogą być uznane za duplikaty.
        """
        firma = _klucz_faktury(dane.dostawca)
        numer = _klucz_faktury(dane.numer)
        rows = self.db.execute(
            "SELECT r.id, r.dokument_id, r.dostawca, r.numer, "
            "d.nazwa_zrodlowa FROM rachunki r "
            "JOIN dokumenty d ON d.id = r.dokument_id ORDER BY r.id"
        ).fetchall()
        return [
            row for row in rows
            if row["dokument_id"] == dane.dokument_id
            or (firma and numer and
                _klucz_faktury(row["dostawca"]) == firma and
                _klucz_faktury(row["numer"]) == numer)
        ]

    def znajdz_duplikat(self, dane: DaneRachunku) -> sqlite3.Row | None:
        """Do wyświetlenia potwierdzenia; metoda nie zmienia bazy."""
        rows = self._pasujace_faktury(dane)
        if len(rows) > 1:
            raise ValueError(
                "Znaleziono kilka pasujących zapisów. "
                "Rozstrzygnij duplikaty przed nadpisaniem faktury."
            )
        return rows[0] if rows else None

    def zapisz_rachunek(self, dane: DaneRachunku, *,
                        nadpisz_id: int | None = None) -> int:
        """Nowy zapis bez zgody; zastąpienie tylko wskazanego ID po potwierdzeniu."""
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
            # Sprawdź identyfikację ponownie W TRANSAKCJI, aby warstwa
            # GUI lub inny kod nie mógł zapisać duplikatu bez zgody.
            dopasowania = self._pasujace_faktury(dane)
            if len(dopasowania) > 1:
                raise ValueError(
                    "Znaleziono kilka pasujących faktur. "
                    "Nie można bezpiecznie zdecydować, którą nadpisać."
                )
            istnieje = dopasowania[0] if dopasowania else None
            if istnieje and nadpisz_id is None:
                raise FakturaJuzIstnieje(int(istnieje["id"]))
            if nadpisz_id is not None and (
                type(nadpisz_id) is not int or not istnieje
                or int(istnieje["id"]) != nadpisz_id
            ):
                raise ValueError(
                    "Potwierdzenie dotyczy innej faktury. "
                    "Odśwież dane przed zapisem."
                )
            wartosci = (dostawca, dane.numer.strip(), wystawiono, termin, od, do,
                       kwota, dane.status, dane.uwagi.strip(), numer_konta)
            if istnieje:
                rachunek_id = int(istnieje["id"])
                self.db.execute(
                    "UPDATE rachunki SET dokument_id=?, dostawca=?, numer=?, data_wystawienia=?, "
                    "termin_platnosci=?, okres_od=?, okres_do=?, kwota_grosze=?, "
                    "status=?, uwagi=?, numer_konta=?, zmieniono_utc=strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
                    "WHERE id=?", (dane.dokument_id, *wartosci, rachunek_id)
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
