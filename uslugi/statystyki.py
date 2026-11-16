# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Zestawienia aktywnych faktur w groszach, wyłącznie z lokalnej SQLite."""
from __future__ import annotations

import sqlite3
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import groupby
from typing import Iterable

from uslugi.finanse import DATA_ROZLICZENIOWA_SQL


BEZ_KATEGORII = "bez_kategorii"


@dataclass(frozen=True)
class ZakresDat:
    od: date
    do: date

    def __post_init__(self):
        if self.od > self.do:
            raise ValueError("Początek zakresu jest późniejszy niż koniec")

    def poprzedni(self) -> ZakresDat | None:
        if self.od == date.min:
            return None
        koniec = self.od - timedelta(days=1)
        if (self.od.month, self.od.day, self.do.month, self.do.day) == (1, 1, 12, 31):
            if self.od.year == self.do.year:
                return ZakresDat(date(koniec.year, 1, 1), koniec)
        if (self.od.year, self.od.month) == (self.do.year, self.do.month):
            if self.od.day == 1 and self.do.day == monthrange(self.do.year, self.do.month)[1]:
                return ZakresDat(koniec.replace(day=1), koniec)
        dlugosc = (self.do - self.od).days + 1
        poczatek = date.fromordinal(max(1, self.od.toordinal() - dlugosc))
        return ZakresDat(poczatek, koniec)


@dataclass
class Suma:
    oplacone: int = 0
    do_zaplaty: int = 0
    liczba: int = 0

    @property
    def razem(self) -> int:
        return self.oplacone + self.do_zaplaty

    def dodaj(self, grosze: int, status: str) -> None:
        if status == "oplacony":
            self.oplacone += grosze
        else:
            self.do_zaplaty += grosze
        self.liczba += 1


@dataclass
class Zestawienie:
    zakres: ZakresDat
    poprzedni_zakres: ZakresDat | None
    biezacy: Suma = field(default_factory=Suma)
    poprzedni: Suma = field(default_factory=Suma)
    okresy: dict[str, Suma] = field(default_factory=lambda: defaultdict(Suma))
    kategorie: dict[int | str, Suma] = field(default_factory=lambda: defaultdict(Suma))
    dostawcy: dict[str, Suma] = field(default_factory=lambda: defaultdict(Suma))


class StatystykiRachunkow:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def opcje_filtrow(self) -> tuple[dict[int, str], list[str]]:
        kategorie = self.db.execute(
            "SELECT k.id,k.nazwa FROM kategorie k WHERE k.aktywna=1 OR EXISTS ("
            "SELECT 1 FROM pozycje_rachunku p JOIN rachunki r ON r.id=p.rachunek_id "
            "WHERE p.kategoria_id=k.id AND r.wycofano_utc IS NULL) "
            "ORDER BY k.nazwa COLLATE NOCASE,k.id"
        )
        dostawcy = self.db.execute(
            "SELECT DISTINCT dostawca FROM rachunki WHERE wycofano_utc IS NULL "
            "ORDER BY dostawca COLLATE NOCASE,dostawca"
        )
        return dict(kategorie), [r[0] for r in dostawcy]

    def zestawienie(
        self, zakres: ZakresDat, *, podstawa: str = "usluga", grupowanie: str = "miesiac",
        kategoria: int | str | None = None, dostawca: str | None = None, status: str | None = None,
    ) -> Zestawienie:
        if podstawa not in {"usluga", "platnosc"}:
            raise ValueError("Nieznana podstawa dat")
        if grupowanie not in {"miesiac", "rok"}:
            raise ValueError("Nieznane grupowanie okresów")
        if status not in {None, "oplacony", "do_zaplaty"}:
            raise ValueError("Nieznany status płatności")

        poprzedni = zakres.poprzedni()
        raport = Zestawienie(zakres, poprzedni)
        od = poprzedni.od if poprzedni else zakres.od
        poczatek = zakres.od.isoformat()
        data_raportu = "r.data_oplacenia" if podstawa == "platnosc" else DATA_ROZLICZENIOWA_SQL
        filtry = ["r.wycofano_utc IS NULL", f"{data_raportu} BETWEEN :od AND :do"]
        parametry = {"od": od.isoformat(), "do": zakres.do.isoformat()}
        if podstawa == "platnosc":
            filtry.append("r.status='oplacony'")
        if status is not None:
            filtry.append("r.status=:status")
            parametry["status"] = status
        if dostawca is not None:
            filtry.append("r.dostawca=:dostawca")
            parametry["dostawca"] = dostawca

        pozycje = self.db.execute(
            f"""
            WITH faktury AS (
                SELECT r.id,r.kwota_grosze,r.status,r.dostawca,{data_raportu} AS data_raportu
                FROM rachunki r WHERE {" AND ".join(filtry)}
            )
            SELECT f.*,p.kategoria_id,SUM(p.kwota_grosze) AS kwota_pozycji
            FROM faktury f LEFT JOIN pozycje_rachunku p ON p.rachunek_id=f.id
            GROUP BY f.id,p.kategoria_id ORDER BY f.id
            """,
            parametry,
        )
        dlugosc_klucza = 7 if grupowanie == "miesiac" else 4
        for _, wiersze in groupby(pozycje, key=lambda w: w["id"]):
            faktura = next(wiersze)
            kwoty_kategorii = _kwoty_kategorii(faktura, wiersze)
            kwota = faktura["kwota_grosze"]
            if kategoria is not None:
                if kategoria not in kwoty_kategorii:
                    continue
                kwota = kwoty_kategorii[kategoria]
                kwoty_kategorii = {kategoria: kwota}
            stan, dzien = faktura["status"], faktura["data_raportu"]
            if dzien < poczatek:
                raport.poprzedni.dodaj(kwota, stan)
                continue
            raport.biezacy.dodaj(kwota, stan)
            raport.okresy[dzien[:dlugosc_klucza]].dodaj(kwota, stan)
            raport.dostawcy[faktura["dostawca"]].dodaj(kwota, stan)
            for ident, kwota_pozycji in kwoty_kategorii.items():
                raport.kategorie[ident].dodaj(kwota_pozycji, stan)
        return raport


def _kwoty_kategorii(
    faktura: sqlite3.Row, pozostale_wiersze: Iterable[sqlite3.Row],
) -> dict[int | str, int]:
    """Rozdziel wyłącznie kwoty wynikające z pozycji i nagłówka."""
    kwota = faktura["kwota_grosze"]
    if faktura["kategoria_id"] is None:
        return {BEZ_KATEGORII: kwota}
    kwoty = {faktura["kategoria_id"]: faktura["kwota_pozycji"]}
    kwoty.update((wiersz["kategoria_id"], wiersz["kwota_pozycji"])
                 for wiersz in pozostale_wiersze)
    roznica = kwota - sum(kwoty.values())
    if roznica < 0:
        return {BEZ_KATEGORII: kwota}
    if roznica:
        kwoty[BEZ_KATEGORII] = roznica
    return kwoty
