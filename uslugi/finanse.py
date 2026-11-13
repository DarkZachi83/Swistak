# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Świstak — jawne operacje finansowe, kompletność cykli i dziennik zmian.

Wszystkie operacje zmieniające finanse wykonuje warstwa usług po działaniu
użytkownika. Moduł nie jest narzędziem zapisowym Agenta LLM.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any

from baza.polaczenie import transakcja


def _data(wartosc: str) -> str:
    if not isinstance(wartosc, str) or len(wartosc) != 10:
        raise ValueError("Data musi mieć format RRRR-MM-DD")
    if date.fromisoformat(wartosc).isoformat() != wartosc:
        raise ValueError("Nieprawidłowa data")
    return wartosc


def cykl_miesiaca(tekst: str) -> str:
    if (not isinstance(tekst, str) or len(tekst) != 7
            or not tekst[:4].isdigit() or tekst[4] != "-"):
        raise ValueError("Cykl musi mieć format RRRR-MM")
    date.fromisoformat(tekst + "-01")
    return tekst


def cykl_faktury(wiersz: sqlite3.Row | dict[str, Any]) -> str | None:
    koniec = wiersz["okres_do"] or wiersz["data_wystawienia"]
    return cykl_miesiaca(koniec[:7]) if koniec else None


def _faktura_pola(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    # Dziennik nie zawiera numerów kont, treści dokumentu ani OCR.
    keys = ("id", "dokument_id", "dostawca", "numer",
            "kwota_grosze", "termin_platnosci",
            "okres_od", "okres_do", "data_wystawienia", "status",
            "data_oplacenia", "wycofano_utc", "powod_wycofania",
            "wersja_rekordu")
    return {key: row[key] for key in keys}


def zdarzenie(
    db: sqlite3.Connection, typ: str, ident: int | str, operacja: str,
    *, przed: dict | None = None, po: dict | None = None,
    powod: str = "", zrodlo: str = "user",
) -> None:
    if zrodlo not in ("user", "system"):
        raise ValueError("Nieprawidłowe źródło zdarzenia")
    db.execute(
        "INSERT INTO dziennik_zdarzen(obiekt_typ,obiekt_id,operacja,przed_json,po_json,powod,zrodlo) "
        "VALUES (?,?,?,?,?,?,?)",
        (typ, str(ident), operacja,
         json.dumps(przed, ensure_ascii=False, sort_keys=True) if przed is not None else None,
         json.dumps(po, ensure_ascii=False, sort_keys=True) if po is not None else None,
         powod[:400], zrodlo),
    )


def uniewaznij_kompletnosc(db: sqlite3.Connection, cykl: str | None, powod: str) -> bool:
    """Wywoływać w tej samej transakcji co zmiana zestawu dokumentów."""
    if cykl is None:
        return False
    cykl_miesiaca(cykl)
    row = db.execute(
        "SELECT * FROM cykle_rozliczeniowe WHERE cykl=? AND potwierdzono_kompletnosc=1",
        (cykl,),
    ).fetchone()
    if row is None:
        return False
    db.execute(
        "UPDATE cykle_rozliczeniowe SET potwierdzono_kompletnosc=0, "
        "potwierdzono_utc=NULL, brak_rachunkow_potwierdzony=0, "
        "uniewazniono_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
        "powod_uniewaznienia=? WHERE cykl=?", (powod[:400],cykl),
    )
    zdarzenie(db, "cycle", cykl, "uniewaznienie_kompletnosci",
              przed={"kompletne": True}, po={"kompletne": False}, powod=powod,
              zrodlo="system")
    return True


class Finanse:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def _faktura(self, ident: int) -> sqlite3.Row:
        if type(ident) is not int or ident <= 0:
            raise ValueError("Niepoprawny identyfikator faktury")
        row = self.db.execute("SELECT * FROM rachunki WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise ValueError("Nie znaleziono faktury")
        return row

    @staticmethod
    def _wersja(row: sqlite3.Row, expected_version: int | None) -> None:
        if expected_version is not None and row["wersja_rekordu"] != expected_version:
            raise ValueError("Faktura zmieniła się od czasu jej otwarcia; odśwież widok")

    def ustaw_oplacona(
        self, ident: int, data_oplacenia: str,
        *, expected_version: int | None = None,
    ) -> None:
        dzien = _data(data_oplacenia)
        with transakcja(self.db):
            before = self._faktura(ident)
            self._wersja(before, expected_version)
            if before["wycofano_utc"]:
                raise ValueError("Nie można opłacić wycofanej faktury")
            if before["status"] == "oplacony" and before["data_oplacenia"] == dzien:
                return
            self.db.execute(
                "UPDATE rachunki SET status='oplacony', data_oplacenia=?, "
                "wersja_rekordu=wersja_rekordu+1, "
                "zmieniono_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (dzien,ident),
            )
            after = self._faktura(ident)
            zdarzenie(self.db, "invoice", ident, "oplacenie",
                      przed=_faktura_pola(before), po=_faktura_pola(after))

    def cofnij_oplacenie(
        self, ident: int, *, powod: str, expected_version: int | None = None,
    ) -> None:
        if not powod.strip():
            raise ValueError("Cofnięcie opłacenia wymaga podania powodu")
        with transakcja(self.db):
            before = self._faktura(ident)
            self._wersja(before, expected_version)
            if before["wycofano_utc"] or before["status"] != "oplacony":
                raise ValueError("Faktura nie jest aktywnym opłaconym rachunkiem")
            self.db.execute(
                "UPDATE rachunki SET status='do_zaplaty', data_oplacenia=NULL, "
                "wersja_rekordu=wersja_rekordu+1, "
                "zmieniono_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (ident,),
            )
            zdarzenie(self.db, "invoice", ident, "cofniecie_oplacenia",
                      przed=_faktura_pola(before),
                      po=_faktura_pola(self._faktura(ident)), powod=powod)

    def wycofaj(self, ident: int, *, powod: str, expected_version: int | None = None) -> None:
        if not powod.strip():
            raise ValueError("Wycofanie wymaga podania powodu")
        with transakcja(self.db):
            before = self._faktura(ident)
            self._wersja(before, expected_version)
            if before["wycofano_utc"]:
                raise ValueError("Faktura została już wycofana")
            self.db.execute(
                "UPDATE rachunki SET wycofano_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                "powod_wycofania=?, wersja_rekordu=wersja_rekordu+1, "
                "zmieniono_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (powod[:400],ident),
            )
            zdarzenie(self.db, "invoice", ident, "wycofanie",
                      przed=_faktura_pola(before),
                      po=_faktura_pola(self._faktura(ident)), powod=powod)
            uniewaznij_kompletnosc(self.db, cykl_faktury(before),
                                   "Wycofano fakturę " + str(ident))

    def przywroc(self, ident: int, *, powod: str, expected_version: int | None = None) -> None:
        if not powod.strip():
            raise ValueError("Przywrócenie wymaga podania powodu")
        with transakcja(self.db):
            before = self._faktura(ident)
            self._wersja(before, expected_version)
            if not before["wycofano_utc"]:
                raise ValueError("Faktura nie jest wycofana")
            if before["numer"].strip():
                rows = self.db.execute(
                    "SELECT dostawca,numer FROM rachunki "
                    "WHERE id<>? AND wycofano_utc IS NULL AND trim(numer)<>''",
                    (ident,),
                ).fetchall()
                norm = lambda t: " ".join(t.split()).casefold()
                if any(norm(row["dostawca"]) == norm(before["dostawca"])
                       and norm(row["numer"]) == norm(before["numer"]) for row in rows):
                    raise ValueError("Aktywna faktura ma tego samego dostawcę i numer")
            self.db.execute(
                "UPDATE rachunki SET wycofano_utc=NULL, powod_wycofania=NULL, "
                "wersja_rekordu=wersja_rekordu+1, "
                "zmieniono_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (ident,),
            )
            zdarzenie(self.db, "invoice", ident, "przywrocenie",
                      przed=_faktura_pola(before),
                      po=_faktura_pola(self._faktura(ident)), powod=powod)
            uniewaznij_kompletnosc(self.db, cykl_faktury(before),
                                   "Przywrócono fakturę " + str(ident))

    def ocena_cyklu(self, cykl: str, *, dzisiaj: str | None = None) -> dict:
        cykl_miesiaca(cykl)
        dzis = date.fromisoformat(_data(dzisiaj)) if dzisiaj else date.today()
        rows = self.db.execute(
            "SELECT status,kwota_grosze FROM rachunki "
            "WHERE wycofano_utc IS NULL "
            "AND substr(COALESCE(okres_do,data_wystawienia),1,7)=?",
            (cykl,),
        ).fetchall()
        monthly = self.db.execute(
            "SELECT potwierdzono_kompletnosc,brak_rachunkow_potwierdzony "
            "FROM cykle_rozliczeniowe WHERE cykl=?", (cykl,),
        ).fetchone()
        confirmed = bool(monthly and monthly["potwierdzono_kompletnosc"])
        unpaid = [r for r in rows if r["status"] != "oplacony"]
        missing = self.db.execute(
            "SELECT COUNT(*) FROM oczekiwane_dokumenty o "
            "JOIN profile_rachunkow p ON p.id=o.profil_id "
            "WHERE o.cykl=? AND (o.wyjatek IS NULL OR o.wyjatek='niepewne') "
            "AND o.oczekiwany_od<=? AND NOT EXISTS("
            "SELECT 1 FROM powiazania_oczekiwanych l JOIN rachunki r ON r.id=l.rachunek_id "
            "WHERE l.oczekiwany_id=o.id AND r.wycofano_utc IS NULL)",
            (cykl,dzis.isoformat()),
        ).fetchone()[0]
        month_ended = cykl < dzis.strftime("%Y-%m")
        return {
            "cycle": cykl, "finished": month_ended, "documents_confirmed": confirmed,
            "invoice_count": len(rows), "unpaid_count": len(unpaid),
            "unpaid_grosze": sum(int(r["kwota_grosze"]) for r in unpaid),
            "missing_expected": missing,
            "closed": bool(month_ended and confirmed and not unpaid and not missing),
        }

    def potwierdz_kompletnosc(
        self, cykl: str, *, brak_rachunkow: bool = False, dzisiaj: str | None = None,
    ) -> None:
        cykl_miesiaca(cykl)
        # Nie można zatwierdzić kompletności, zanim aktywne harmonogramy
        # zostały zmaterializowane jako oczekiwane dokumenty.
        from uslugi.plan_rachunkow import PlanRachunkow
        PlanRachunkow(self.db).generuj_oczekiwania(cykl)
        with transakcja(self.db):
            assessment = self.ocena_cyklu(cykl, dzisiaj=dzisiaj)
            if not assessment["finished"]:
                raise ValueError("Nie można zamknąć bieżącego lub przyszłego miesiąca")
            if assessment["missing_expected"]:
                raise ValueError("Najpierw rozstrzygnij brakujące dokumenty")
            if not assessment["invoice_count"] and not brak_rachunkow:
                raise ValueError("Pusty miesiąc wymaga świadomego potwierdzenia braku rachunków")
            before = self.db.execute(
                "SELECT potwierdzono_kompletnosc,brak_rachunkow_potwierdzony "
                "FROM cykle_rozliczeniowe WHERE cykl=?", (cykl,),
            ).fetchone()
            prev = dict(before) if before else None
            self.db.execute(
                "INSERT INTO cykle_rozliczeniowe(cykl,potwierdzono_kompletnosc,potwierdzono_utc,"
                "brak_rachunkow_potwierdzony,uniewazniono_utc,powod_uniewaznienia) "
                "VALUES (?,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,NULL,NULL) "
                "ON CONFLICT(cykl) DO UPDATE SET potwierdzono_kompletnosc=1, "
                "potwierdzono_utc=excluded.potwierdzono_utc, "
                "brak_rachunkow_potwierdzony=excluded.brak_rachunkow_potwierdzony, "
                "uniewazniono_utc=NULL,powod_uniewaznienia=NULL",
                (cykl,int(brak_rachunkow and not assessment["invoice_count"])),
            )
            zdarzenie(self.db, "cycle", cykl, "potwierdzenie_kompletnosci",
                      przed=prev, po={"kompletne": True,
                                      "brak_rachunkow": bool(brak_rachunkow and not assessment["invoice_count"])})

    def dziennik(self, typ: str, ident: int | str, *, limit: int = 50) -> list[dict]:
        if typ not in ("invoice","profile","cycle","expectation") or type(limit) is not int or not 1<=limit<=200:
            raise ValueError("Niepoprawne parametry dziennika")
        return [dict(row) for row in self.db.execute(
            "SELECT id,utworzono_utc,obiekt_typ,obiekt_id,operacja,przed_json,po_json,powod,zrodlo "
            "FROM dziennik_zdarzen WHERE obiekt_typ=? AND obiekt_id=? "
            "ORDER BY id DESC LIMIT ?",(typ,str(ident),limit))]
