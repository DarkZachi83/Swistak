# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Historia i rozliczenia miesięczne — sprawdzalne sumy, bez zgadywania dat."""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from uslugi.finanse import Finanse, _data, cykl_miesiaca


class HistoriaRozliczen:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.finanse = Finanse(db)

    def miesiace(self, *, limit: int = 120) -> list[str]:
        if type(limit) is not int or not 1 <= limit <= 240:
            raise ValueError("Niepoprawny limit miesięcy")
        rows = self.db.execute(
            "SELECT cykl FROM ("
            "SELECT substr(COALESCE(okres_do,data_wystawienia),1,7) AS cykl "
            "FROM rachunki WHERE COALESCE(okres_do,data_wystawienia) IS NOT NULL "
            "UNION SELECT substr(data_oplacenia,1,7) AS cykl FROM rachunki "
            "WHERE data_oplacenia IS NOT NULL "
            "UNION SELECT cykl FROM oczekiwane_dokumenty "
            "UNION SELECT cykl FROM cykle_rozliczeniowe"
            ") WHERE cykl IS NOT NULL AND length(cykl)=7 "
            "ORDER BY cykl DESC LIMIT ?",(limit,)
        ).fetchall()
        return [r["cykl"] for r in rows]

    def faktury(self, cykl: str) -> list[dict[str, Any]]:
        cykl_miesiaca(cykl)
        return [dict(r) for r in self.db.execute(
            "SELECT id,dokument_id,dostawca,numer,kwota_grosze,status,"
            "termin_platnosci,data_oplacenia,wycofano_utc,wersja_rekordu,"
            "okres_do,data_wystawienia "
            "FROM rachunki "
            "WHERE substr(COALESCE(okres_do,data_wystawienia),1,7)=? "
            "ORDER BY id DESC LIMIT 500",(cykl,)
        )]

    def oczekiwania(self, cykl: str, *, dzisiaj: str | None = None) -> list[dict]:
        cykl_miesiaca(cykl)
        now = _data(dzisiaj) if dzisiaj is not None else date.today().isoformat()
        rows = self.db.execute(
            "SELECT o.id,o.profil_id,p.nazwa,p.dostawca,o.cykl,o.oczekiwany_od,"
            "o.wyjatek,o.powod_wyjatku,"
            "GROUP_CONCAT(CASE WHEN r.wycofano_utc IS NULL THEN r.id ELSE NULL END)"
            " AS powiazane_faktury "
            "FROM oczekiwane_dokumenty o "
            "JOIN profile_rachunkow p ON p.id=o.profil_id "
            "LEFT JOIN powiazania_oczekiwanych l ON l.oczekiwany_id=o.id "
            "LEFT JOIN rachunki r ON r.id=l.rachunek_id "
            "WHERE o.cykl=? GROUP BY o.id ORDER BY p.nazwa,o.id",(cykl,)
        )
        results=[]
        for row in rows:
            item=dict(row)
            links=item["powiazane_faktury"]
            item["invoice_ids"] = [int(x) for x in links.split(",")] if links else []
            del item["powiazane_faktury"]
            if item["invoice_ids"]:
                status="received"
            elif item["wyjatek"] == "nie_wystawiono":
                status="not_issued"
            elif item["wyjatek"] == "niepewne":
                status="uncertain"
            elif item["oczekiwany_od"] <= now:
                status="missing"
            else:
                status="waiting"
            item["state"]=status
            results.append(item)
        return results

    def profile(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT p.id,p.nazwa,p.dostawca,p.kategoria_id,p.aktywny,"
            "k.nazwa AS kategoria,h.wersja,h.typ,h.co_ile_miesiecy,"
            "h.cykl_od,h.cykl_do,h.cykl_kotwicy,h.przesuniecie_dni "
            "FROM profile_rachunkow p "
            "LEFT JOIN kategorie k ON k.id=p.kategoria_id "
            "LEFT JOIN harmonogramy_rachunkow h ON h.id=("
            "SELECT MAX(id) FROM harmonogramy_rachunkow WHERE profil_id=p.id) "
            "ORDER BY p.aktywny DESC,p.nazwa,p.id LIMIT 500"
        )]

    def miesiac(self, cykl: str, *, dzisiaj: str | None = None) -> dict:
        cykl_miesiaca(cykl)
        current = self.finanse.ocena_cyklu(cykl,dzisiaj=dzisiaj)
        invoices = self.faktury(cykl)
        active=[r for r in invoices if r["wycofano_utc"] is None]
        active_total=sum(int(r["kwota_grosze"]) for r in active)
        paid_total=sum(int(r["kwota_grosze"]) for r in active if r["status"]=="oplacony")
        payments_month=self.db.execute(
            "SELECT COALESCE(SUM(kwota_grosze),0) AS suma,COUNT(*) AS ile "
            "FROM rachunki WHERE wycofano_utc IS NULL AND status='oplacony' "
            "AND substr(data_oplacenia,1,7)=?",(cykl,)
        ).fetchone()
        expected=self.oczekiwania(cykl,dzisiaj=dzisiaj)
        return {
            **current,
            "billed_grosze": active_total,
            "paid_service_grosze": paid_total,
            "payments_in_month_grosze": int(payments_month["suma"]),
            "payments_in_month_count": int(payments_month["ile"]),
            "withdrawn_count": len(invoices)-len(active),
            "uncertain_count": sum(row["state"]=="uncertain" for row in expected),
            "expected_count": len(expected),
            "unresolved_count": sum(row["state"] not in {"received","not_issued"}
                                    for row in expected),
        }

    def dziennik_miesiaca(self, cykl: str, *, limit: int = 200) -> list[dict]:
        cykl_miesiaca(cykl)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("Niepoprawny limit dziennika")
        # Rejestrujemy zdarzenia zarówno faktur za wybrany miesiąc,
        # jak i płatności faktycznie wykonanych w wybranym miesiącu.
        # Nie dopisujemy zdarzeń z dowolnego, niezwiązanego profilu.
        invoice_ids=set(str(r["id"]) for r in self.faktury(cykl))
        invoice_ids.update(str(r["id"]) for r in self.db.execute(
            "SELECT id FROM rachunki WHERE substr(data_oplacenia,1,7)=?",
            (cykl,),
        ))
        expectation_ids=[str(r["id"]) for r in self.oczekiwania(cykl)]
        profile_ids=set(str(r["profil_id"]) for r in self.oczekiwania(cykl))
        profile_ids.update(str(r["profil_id"]) for r in self.db.execute(
            "SELECT DISTINCT profil_id FROM harmonogramy_rachunkow "
            "WHERE cykl_od<=? AND (cykl_do IS NULL OR cykl_do>=?)",
            (cykl,cykl),
        ))
        # Bez swobodnego konkatenowania parametrów SQL.
        conditions=["(obiekt_typ='cycle' AND obiekt_id=?)"]
        values: list[str | int]=[cykl]
        for kind, identifiers in [("invoice",sorted(invoice_ids)),
                                  ("expectation",expectation_ids),
                                  ("profile",sorted(profile_ids))]:
            if identifiers:
                placeholders=",".join("?" for _ in identifiers)
                conditions.append(
                    f"(obiekt_typ='{kind}' AND obiekt_id IN ({placeholders}))"
                )
                values.extend(identifiers)
        query=(
            "SELECT id,utworzono_utc,obiekt_typ,obiekt_id,operacja,powod,zrodlo "
            "FROM dziennik_zdarzen WHERE " + " OR ".join(conditions) +
            " ORDER BY id DESC LIMIT ?"
        )
        values.append(limit)
        return [dict(r) for r in self.db.execute(query,values)]
