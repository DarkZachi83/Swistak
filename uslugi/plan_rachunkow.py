# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Plan rachunków — jawne profile i harmonogramy, bez generowania faktur."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from baza.polaczenie import transakcja
from uslugi.finanse import cykl_miesiaca, zdarzenie, uniewaznij_kompletnosc

_TYPS = ("miesieczny", "co_n_miesiecy", "nieregularny")


def _miesiac(tekst: str) -> date:
    cykl_miesiaca(tekst)
    return date.fromisoformat(tekst + "-01")


def _nast_miesiac(d: date) -> date:
    return date(d.year + (d.month == 12), (d.month % 12) + 1, 1)


def _pop_miesiac(d: date) -> date:
    return date(d.year - (d.month == 1), ((d.month + 10) % 12) + 1, 1)


def _miesiecy_od(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + a.month - b.month


def _sprawdz(typ: str, co_ile: int, kotwica: str, od: str, przesuniecie: int) -> None:
    if typ not in _TYPS or type(co_ile) is not int or not (1 <= co_ile <= 120):
        raise ValueError("Niepoprawna częstotliwość harmonogramu")
    _miesiac(kotwica)
    _miesiac(od)
    if type(przesuniecie) is not int or not -62 <= przesuniecie <= 180:
        raise ValueError("Niepoprawne przesunięcie oczekiwania")
    if typ == "miesieczny" and co_ile != 1:
        raise ValueError("Miesięczny profil musi mieć interwał 1 miesiąca")


class PlanRachunkow:
    """Profile zatwierdzane przez użytkownika, nigdy automatycznie przez AI."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def utworz_profil(
        self, nazwa: str, *, dostawca: str = "", kategoria_id: int | None = None,
        typ: str = "miesieczny", co_ile_miesiecy: int = 1,
        cykl_od: str, cykl_kotwicy: str | None = None, przesuniecie_dni: int = 0,
    ) -> int:
        nazwa = " ".join(nazwa.split())
        dostawca = " ".join(dostawca.split())
        if not nazwa or len(nazwa) > 120 or len(dostawca) > 200:
            raise ValueError("Niepoprawna nazwa lub dostawca profilu")
        kotwica = cykl_kotwicy or cykl_od
        _sprawdz(typ, co_ile_miesiecy, kotwica, cykl_od, przesuniecie_dni)
        with transakcja(self.db):
            if kategoria_id is not None and not self.db.execute(
                "SELECT 1 FROM kategorie WHERE id=? AND aktywna=1", (kategoria_id,),
            ).fetchone():
                raise ValueError("Nieznana kategoria")
            cur = self.db.execute(
                "INSERT INTO profile_rachunkow(nazwa,dostawca,kategoria_id) VALUES (?,?,?)",
                (nazwa, dostawca, kategoria_id),
            )
            ident = int(cur.lastrowid)
            self.db.execute(
                "INSERT INTO harmonogramy_rachunkow"
                "(profil_id,wersja,cykl_od,typ,co_ile_miesiecy,cykl_kotwicy,przesuniecie_dni)"
                "VALUES (?,1,?,?,?,?,?)",
                (ident,cykl_od,typ,co_ile_miesiecy,kotwica,przesuniecie_dni),
            )
            zdarzenie(self.db, "profile", ident, "utworzenie",
                      po={"nazwa": nazwa, "dostawca": dostawca,
                          "typ": typ, "cykl_od": cykl_od, "kotwica": kotwica})
        return ident

    def zmien_harmonogram(
        self, profil_id: int, *, cykl_od: str, typ: str,
        co_ile_miesiecy: int = 1, cykl_kotwicy: str | None = None,
        przesuniecie_dni: int = 0,
    ) -> int:
        _miesiac(cykl_od)
        kotwica = cykl_kotwicy or cykl_od
        _sprawdz(typ,co_ile_miesiecy,kotwica,cykl_od,przesuniecie_dni)
        with transakcja(self.db):
            row = self.db.execute(
                "SELECT h.* FROM harmonogramy_rachunkow h "
                "JOIN profile_rachunkow p ON p.id=h.profil_id "
                "WHERE h.profil_id=? AND p.aktywny=1 "
                "ORDER BY h.wersja DESC LIMIT 1", (profil_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Nie znaleziono aktywnego profilu")
            if cykl_od <= row["cykl_od"]:
                raise ValueError("Nowa wersja harmonogramu musi zaczynać się później")
            self.db.execute(
                "UPDATE harmonogramy_rachunkow SET cykl_do=? WHERE id=?",
                (_pop_miesiac(_miesiac(cykl_od)).strftime("%Y-%m"), row["id"]),
            )
            wersja = int(row["wersja"])+1
            self.db.execute(
                "INSERT INTO harmonogramy_rachunkow"
                "(profil_id,wersja,cykl_od,typ,co_ile_miesiecy,cykl_kotwicy,przesuniecie_dni) "
                "VALUES (?,?,?,?,?,?,?)",
                (profil_id,wersja,cykl_od,typ,co_ile_miesiecy,kotwica,przesuniecie_dni),
            )
            zdarzenie(self.db, "profile", profil_id, "zmiana_harmonogramu",
                      przed={"wersja": row["wersja"], "od": row["cykl_od"],
                             "typ": row["typ"]},
                      po={"wersja": wersja, "od": cykl_od, "typ": typ})
            # Retroaktywna zmiana profilu może podważać zamknięcia.
            confirmed = self.db.execute(
                "SELECT cykl FROM cykle_rozliczeniowe WHERE cykl>=? "
                "AND potwierdzono_kompletnosc=1", (cykl_od,),
            ).fetchall()
            for rec in confirmed:
                uniewaznij_kompletnosc(
                    self.db, rec["cykl"], "Zmiana harmonogramu profilu " + str(profil_id)
                )
            return wersja

    def generuj_oczekiwania(self, cykl: str) -> list[int]:
        """Idempotentnie utwórz oczekiwania dla zatwierdzonych profili.

        Nieregularne profile oraz cykle sprzed aktywacji nie tworzą alertów.
        Wymagany jawny wybór miesiąca — brak seryjnego generowania historii.
        """
        current = _miesiac(cykl)
        created: list[int] = []
        with transakcja(self.db):
            rows = self.db.execute(
                "SELECT h.*, p.aktywny FROM harmonogramy_rachunkow h "
                "JOIN profile_rachunkow p ON p.id=h.profil_id "
                "WHERE p.aktywny=1 AND h.cykl_od<=? "
                "AND (h.cykl_do IS NULL OR h.cykl_do>=?)", (cykl,cykl)
            ).fetchall()
            for h in rows:
                if h["typ"] == "nieregularny":
                    continue
                delta = _miesiecy_od(current, _miesiac(h["cykl_kotwicy"]))
                if delta < 0 or delta % int(h["co_ile_miesiecy"]) != 0:
                    continue
                expected = (_nast_miesiac(current) + timedelta(days=h["przesuniecie_dni"])).isoformat()
                exists = self.db.execute(
                    "SELECT 1 FROM oczekiwane_dokumenty WHERE profil_id=? AND cykl=?",
                    (h["profil_id"],cykl),
                ).fetchone()
                if exists:
                    continue
                cursor = self.db.execute(
                    "INSERT INTO oczekiwane_dokumenty(profil_id,harmonogram_id,cykl,oczekiwany_od) "
                    "VALUES (?,?,?,?)", (h["profil_id"],h["id"],cykl,expected),
                )
                ident = int(cursor.lastrowid)
                created.append(ident)
                zdarzenie(self.db, "expectation", ident, "utworzenie",
                          po={"profil_id":h["profil_id"],"cykl":cykl,
                              "oczekiwany_od":expected}, zrodlo="system")
            if created:
                uniewaznij_kompletnosc(
                    self.db, cykl, "Utworzono oczekiwane dokumenty dla cyklu"
                )
        return created

    def oznacz_wyjatek(self, oczekiwany_id: int, *, typ: str, powod: str) -> None:
        if typ not in ("nie_wystawiono","niepewne") or not powod.strip():
            raise ValueError("Wyjaśnienie brakującego dokumentu jest wymagane")
        with transakcja(self.db):
            row = self.db.execute(
                "SELECT * FROM oczekiwane_dokumenty WHERE id=?", (oczekiwany_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Nie znaleziono oczekiwania")
            before = {"wyjatek":row["wyjatek"],"powod":row["powod_wyjatku"]}
            self.db.execute(
                "UPDATE oczekiwane_dokumenty SET wyjatek=?, powod_wyjatku=? WHERE id=?",
                (typ,powod[:400],oczekiwany_id)
            )
            zdarzenie(self.db, "expectation", oczekiwany_id, "wyjatek",
                      przed=before, po={"wyjatek":typ,"powod":powod[:400]}, powod=powod)
            uniewaznij_kompletnosc(self.db,row["cykl"],"Zmieniono wyjątek oczekiwania")

    def powiaz(self, oczekiwany_id: int, rachunek_id: int) -> None:
        with transakcja(self.db):
            expected = self.db.execute(
                "SELECT * FROM oczekiwane_dokumenty WHERE id=?", (oczekiwany_id,),
            ).fetchone()
            invoice = self.db.execute(
                "SELECT id,wycofano_utc FROM rachunki WHERE id=?", (rachunek_id,),
            ).fetchone()
            if expected is None or invoice is None or invoice["wycofano_utc"]:
                raise ValueError("Oczekiwanie lub aktywna faktura nie istnieje")
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO powiazania_oczekiwanych(oczekiwany_id,rachunek_id) "
                "VALUES (?,?)", (oczekiwany_id,rachunek_id),
            )
            if cursor.rowcount:
                zdarzenie(self.db,"expectation",oczekiwany_id,"powiazanie_faktury",
                          po={"rachunek_id":rachunek_id})
                uniewaznij_kompletnosc(
                    self.db,expected["cykl"],"Zmieniono powiązania oczekiwanego dokumentu"
                )

    def odlacz(self, oczekiwany_id: int, rachunek_id: int) -> None:
        with transakcja(self.db):
            row = self.db.execute(
                "SELECT cykl FROM oczekiwane_dokumenty WHERE id=?", (oczekiwany_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Nie znaleziono oczekiwania")
            cursor = self.db.execute(
                "DELETE FROM powiazania_oczekiwanych WHERE oczekiwany_id=? AND rachunek_id=?",
                (oczekiwany_id,rachunek_id),
            )
            if cursor.rowcount:
                zdarzenie(self.db,"expectation",oczekiwany_id,"odlaczenie_faktury",
                          przed={"rachunek_id":rachunek_id})
                uniewaznij_kompletnosc(self.db,row["cykl"],"Odłączono fakturę od oczekiwania")
