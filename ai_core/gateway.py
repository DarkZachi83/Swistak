# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Tool Gateway v1: ścisła allowlista, JSON Schema, brak swobodnego SQL."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from jsonschema import Draft202012Validator, FormatChecker

from .contracts import validate
from .errors import InvalidResponse

CATALOG = Path(__file__).resolve().parents[1] / "docs" / "ai_core" / "tools_v1.json"
MAX_TOOL_OUTPUT_BYTES = 48 * 1024


class ToolGateway:
    """Usługi odczytu: jedna nowa, tylko-odczytowa sesja na zadanie AI.

    Brak API do wykonywania arbitralnego SQL. Każde narzędzie ma stały
    handler i jawnie parametryzowane zapytania. DB nie jest tworzone.
    """

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser().resolve()
        self.data_root = self.database_path.parent
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        if catalog.get("catalog_version") != "1.0" or catalog.get("read_only") is not True:
            raise ValueError("Nieobsługiwana wersja katalogu narzędzi")
        self.catalog = {entry["name"]: entry for entry in catalog["tools"]}
        if len(self.catalog) != len(catalog["tools"]):
            raise ValueError("Powtarzające się nazwy narzędzi")

    def revision(self) -> str:
        """Token bazujący na bajtach pliku SQLite (obecna baza używa DELETE journal).

        Nadaje się do odrzucania wyników po zmianie bazy; nie służy do
        przenoszenia ani synchronizacji bazy między komputerami.
        """
        if not self.database_path.is_file():
            raise FileNotFoundError("Nie znaleziono istniejącej bazy Świstaka")
        digest = hashlib.sha256()
        with self.database_path.open("rb") as fh:
            for piece in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(piece)
        return "db:" + digest.hexdigest()

    def descriptors(self, allowed: list[str]) -> list[dict[str, Any]]:
        result = []
        for name in allowed:
            entry = self.catalog.get(name)
            if entry is None or entry["effect"] != "read":
                raise ValueError("Nieznane lub niedozwolone narzędzie: " + name)
            result.append({"type": "function", "function": {
                "name": name, "description": entry["description"],
                "parameters": entry["input_schema"],
            }})
        return result

    @contextmanager
    def session(self, task: dict[str, Any]) -> Iterator["ToolSession"]:
        validate("TaskRequest", task)
        if task["data_revision"] != self.revision():
            raise InvalidResponse("Zadanie dotyczy nieaktualnej wersji bazy")
        uri = "file:" + quote(str(self.database_path), safe="/") + "?mode=ro"
        db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA foreign_keys=ON")
        # NIE utrzymuj BEGIN na czas generowania LLM: długi read-lock
        # w SQLite DELETE journal zablokowałby GUI przy zapisie faktury.
        # Każdy SELECT wykonuje krótką transakcję tylko do czasu fetch.
        current = ToolSession(self, task, db)
        try:
            yield current
            if task["data_revision"] != self.revision():
                raise InvalidResponse("Baza zmieniła się podczas analizy; wynik jest nieaktualny")
        finally:
            db.close()


class ToolSession:
    """Sesja i rejestr rzeczywiście wykonanych wywołań/dowodów."""

    def __init__(self, gateway: ToolGateway, task: dict[str, Any], db: sqlite3.Connection):
        self.gateway, self.task, self.db = gateway, task, db
        self.results: dict[str, dict[str, Any]] = {}
        self._seen: set[str] = set()
        self._issued = 0
        self._data_version = db.execute("PRAGMA data_version").fetchone()[0]
        self._schema_cache: dict[str, set[str]] = {}

    def issue_call_id(self) -> str:
        self._issued += 1
        return f"{self.task['task_id']}:tool-{self._issued}"

    def columns(self, table: str) -> set[str]:
        if table not in {"rachunki", "dokumenty", "pozycje_rachunku", "kategorie"}:
            return set()
        if table not in self._schema_cache:
            self._schema_cache[table] = {
                row["name"] for row in self.db.execute(f"PRAGMA table_info({table})")
            }
        return self._schema_cache[table]

    def _active_clause(self, alias: str = "r", include: bool = False) -> str:
        if "wycofano_utc" not in self.columns("rachunki") or include:
            return "1=1"
        return f"{alias}.wycofano_utc IS NULL"

    def _get_invoice(self, invoice_id: int, include_withdrawn: bool = False) -> dict[str, Any] | None:
        paid = "r.data_oplacenia" if "data_oplacenia" in self.columns("rachunki") else "NULL"
        withdrawn = "r.wycofano_utc" if "wycofano_utc" in self.columns("rachunki") else "NULL"
        row = self.db.execute(
            "SELECT r.id, r.dokument_id, r.dostawca, r.numer, r.kwota_grosze, "
            "r.status, r.data_wystawienia, r.termin_platnosci, r.okres_od, r.okres_do, "
            + paid + " AS paid_date, " + withdrawn + " AS withdrawn_at, "
            "r.zmieniono_utc FROM rachunki r WHERE r.id=? AND "
            + self._active_clause(include=include_withdrawn), (invoice_id,)
        ).fetchone()
        return dict(row) if row else None

    def _evidence(self, kind: str, source_id: str, call_id: str) -> dict[str, str]:
        return {"source_type": kind, "source_id": source_id,
                "tool_call_id": call_id, "data_revision": self.task["data_revision"]}

    def execute(self, call: dict[str, Any]) -> dict[str, Any]:
        # Zmiana przez inne połączenie po rozpoczęciu analizy
        # oznacza nieaktualność dowodów. Nie mieszaj wersji bazy.
        if self.db.execute("PRAGMA data_version").fetchone()[0] != self._data_version:
            raise InvalidResponse("Baza zmieniła się podczas wykonywania narzędzi")
        validate("ToolCall", call)
        if call["task_id"] != self.task["task_id"] or call["data_revision"] != self.task["data_revision"]:
            raise InvalidResponse("Wywołanie narzędzia pochodzi z innego zadania lub wersji danych")
        if call["call_id"] in self._seen:
            raise InvalidResponse("Powtórzony identyfikator wywołania narzędzia")
        self._seen.add(call["call_id"])
        name = call["tool_name"]
        entry = self.gateway.catalog.get(name)
        if (name not in self.task["allowed_tools"] or entry is None
                or entry["effect"] != "read" or call["tool_version"] != "1.0"):
            return self._error(call, "permission_denied", "Narzędzie nie jest dozwolone")
        validator = Draft202012Validator(entry["input_schema"], format_checker=FormatChecker())
        # Zadanie po zapisie może dotyczyć wyłącznie zmienionej faktury.
        restricted_id = self.task["context"].get("scope_invoice_id")
        if (restricted_id is not None
                and name in {"invoice.details", "invoice.lines", "payment.inspect"}
                and call["arguments"].get("invoice_id") != restricted_id):
            return self._error(call, "permission_denied", "Narzędzie poza zakresem zadania")
        if not validator.is_valid(call["arguments"]):
            return self._error(call, "invalid_arguments", "Nieprawidłowe parametry narzędzia")
        # Terminowość jest liczona WYŁĄCZNIE dla dnia dostarczonego
        # przez hosta (task.context), nie dowolnej daty wymyślonej przez LLM.
        if name == "payment.inspect":
            host_date = self.task["context"].get("reference_date")
            if not host_date or call["arguments"]["reference_date"] != host_date:
                return self._error(call, "invalid_arguments", "Data kontroli musi odpowiadać dacie zadania")
        try:
            data, evidence = self._dispatch(name, call["arguments"], call["call_id"])
            # Nie przekazuj nieograniczonych danych finansowych do kontekstu modelu.
            if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > MAX_TOOL_OUTPUT_BYTES:
                return self._error(call, "invalid_arguments", "Wynik narzędzia przekracza limit rozmiaru")
            result = self._envelope(call, "ok", data, evidence, None)
        except NotImplementedError:
            result = self._error(call, "provider_unavailable", "Ten moduł wymaga przyszłej migracji")
        except (ValueError, LookupError, OSError, sqlite3.Error):
            # Nie ujawniamy ścieżek, numerów kont ani SQL w błędach modelu.
            result = self._error(call, "internal_error", "Narzędzie nie mogło zwrócić danych")
        self.results[call["call_id"]] = result
        return result

    def _envelope(self, call, status, data, evidence, error):
        return validate("ToolResult", {
            "contract_version": "1.0", "task_id": call["task_id"],
            "call_id": call["call_id"], "tool_name": call["tool_name"],
            "status": status, "data": data, "evidence": evidence,
            "error": error, "data_revision": self.task["data_revision"],
        })

    def _error(self, call, code, message):
        result = self._envelope(call, "error", {}, [], {
            "code": code, "message": message,
            "retryable": code in {"provider_unavailable", "timeout"},
        })
        self.results[call["call_id"]] = result
        return result

    def _dispatch(self, name: str, args: dict[str, Any], call_id: str):
        if name == "date.evaluate":
            a, b = date.fromisoformat(args["value"]), date.fromisoformat(args["reference_date"])
            return {"value": a.isoformat(), "reference_date": b.isoformat(),
                    "difference_days": (a - b).days, "is_past": a < b, "is_today": a == b}, []
        if name == "invoice.search":
            return self._search(args, call_id)
        if name == "invoice.details":
            row = self._get_invoice(args["invoice_id"])
            if not row:
                raise LookupError("Nie znaleziono faktury")
            return row, [self._evidence("invoice", str(row["id"]), call_id)]
        if name == "invoice.lines":
            inv = self._get_invoice(args["invoice_id"])
            if not inv:
                raise LookupError("Nie znaleziono faktury")
            rows = self.db.execute(
                "SELECT p.id, p.rachunek_id, p.opis, p.kwota_grosze, k.nazwa AS kategoria "
                "FROM pozycje_rachunku p JOIN kategorie k ON k.id=p.kategoria_id "
                "WHERE p.rachunek_id=? ORDER BY p.id LIMIT ?", (inv["id"], min(100, self.task["limits"]["max_records"]))
            ).fetchall()
            return {"invoice_id": inv["id"], "lines": [dict(row) for row in rows]}, [
                self._evidence("invoice", str(inv["id"]), call_id)]
        if name == "payment.inspect":
            inv = self._get_invoice(args["invoice_id"])
            if inv is None:
                raise LookupError("Nie znaleziono faktury")
            when = date.fromisoformat(args["reference_date"])
            due = date.fromisoformat(inv["termin_platnosci"]) if inv["termin_platnosci"] else None
            unpaid = inv["status"] == "do_zaplaty"
            days_overdue = (when - due).days if due and unpaid and due < when else 0
            days_until = (due - when).days if due else None
            return {"invoice_id": inv["id"], "status": inv["status"], "amount_grosze": inv["kwota_grosze"],
                    "due_date": inv["termin_platnosci"], "reference_date": when.isoformat(),
                    "paid_date": inv["paid_date"], "overdue": bool(days_overdue),
                    "days_overdue": days_overdue,
                    "due_soon_7_days": bool(unpaid and due and 0 <= days_until <= 7)}, [
                self._evidence("invoice", str(inv["id"]), call_id)]
        if name == "finance.aggregate":
            return self._aggregate(args, call_id)
        if name in {"document.verify", "document.extract"}:
            return self._document(name, args, call_id)
        if name == "plan.expected":
            return self._expected(args, call_id)
        if name == "plan.match":
            return self._matches(args, call_id)
        if name == "cycle.evaluate":
            from uslugi.finanse import Finanse
            evaluation = Finanse(self.db).ocena_cyklu(
                args["cycle"], dzisiaj=self.task["context"].get("reference_date")
            )
            return evaluation, [self._evidence("cycle", args["cycle"], call_id)]
        if name == "audit.read":
            typ = args["entity_type"]
            ident = args["entity_id"]
            limit = min(args.get("limit",50),100,self.task["limits"]["max_records"])
            rows = self.db.execute(
                "SELECT id,utworzono_utc,obiekt_typ,obiekt_id,operacja,"
                "przed_json,po_json,powod,zrodlo FROM dziennik_zdarzen "
                "WHERE obiekt_typ=? AND obiekt_id=? ORDER BY id DESC LIMIT ?",
                (typ,ident,limit)
            ).fetchall()
            return {"events":[dict(x) for x in rows]}, [
                self._evidence("audit", str(x["id"]), call_id) for x in rows
            ]
        raise ValueError("Nieobsługiwana operacja")

    def _search(self, args, call_id):
        where = [self._active_clause(include=args.get("include_withdrawn", False))]
        params = []
        if args.get("supplier"):
            where.append("instr(lower(r.dostawca), lower(?)) > 0")
            params.append(args["supplier"])
        if args.get("status") not in (None, "any"):
            where.append("r.status=?")
            params.append(args["status"])
        if args.get("period_from"):
            where.append("COALESCE(r.okres_do,r.data_wystawienia)>=?")
            params.append(args["period_from"])
        if args.get("period_to"):
            where.append("COALESCE(r.okres_do,r.data_wystawienia)<=?")
            params.append(args["period_to"])
        limit = min(args.get("limit", 50), 200, self.task["limits"]["max_records"])
        offset = args.get("offset", 0)
        paid = "r.data_oplacenia" if "data_oplacenia" in self.columns("rachunki") else "NULL"
        sql = ("SELECT r.id, r.dostawca, r.numer, r.kwota_grosze, r.status, "
               "r.data_wystawienia, r.termin_platnosci, r.okres_od, r.okres_do, "
               + paid + " AS paid_date FROM rachunki r WHERE "
               + " AND ".join(where) + " ORDER BY r.id DESC LIMIT ? OFFSET ?")
        rows = [dict(x) for x in self.db.execute(sql, (*params, limit, offset))]
        return {"invoices": rows, "limit": limit, "offset": offset}, [
            self._evidence("invoice", str(row["id"]), call_id) for row in rows]

    def _aggregate(self, args, call_id):
        start, end = args["period_from"], args["period_to"]
        if start > end:
            raise ValueError("Niewłaściwy zakres dat")
        basis = args["basis"]
        group = args.get("group_by", "none")
        if basis == "paid_date" and "data_oplacenia" not in self.columns("rachunki"):
            raise NotImplementedError("Brak rzeczywistych dat opłacenia w obecnej bazie")
        date_expr = ("r.data_oplacenia" if basis == "paid_date"
                     else "COALESCE(r.okres_do,r.data_wystawienia)")
        where = (f"{date_expr} BETWEEN ? AND ? AND " + self._active_clause())
        if basis == "paid_date":
            where += " AND r.status='oplacony'"
        if group == "category":
            # Agregacja po POZYCJACH (bez wielokrotnego zliczania całej faktury).
            sql = ("SELECT k.nazwa AS label, COALESCE(SUM(p.kwota_grosze),0) AS total_grosze "
                   "FROM rachunki r JOIN pozycje_rachunku p ON p.rachunek_id=r.id "
                   "JOIN kategorie k ON k.id=p.kategoria_id "
                   "WHERE " + where + " GROUP BY k.id,k.nazwa ORDER BY k.nazwa LIMIT " + str(min(100, self.task["limits"]["max_records"])))
        else:
            key = {"month": f"substr({date_expr},1,7)",
                   "supplier": "r.dostawca", "none": "'total'"}[group]
            sql = ("SELECT " + key + " AS label, COALESCE(SUM(r.kwota_grosze),0) AS total_grosze "
                   "FROM rachunki r WHERE " + where +
                   " GROUP BY " + key + " ORDER BY label LIMIT " + str(min(100, self.task["limits"]["max_records"])))
        rows = [dict(r) for r in self.db.execute(sql, (start, end))]
        return {"basis": basis, "group_by": group, "groups": rows,
                "total_grosze": sum(r["total_grosze"] for r in rows)}, []

    def _document(self, name, args, call_id):
        row = self.db.execute(
            "SELECT id, sha256, sciezka_wzgledna, rozmiar_bajtow FROM dokumenty WHERE id=?",
            (args["document_id"],)
        ).fetchone()
        if row is None:
            raise LookupError("Nie znaleziono dokumentu")
        # Ochrona przed traversal, symlinkami i uszkodzonym archiwum PDF.
        from uslugi.archiwum import MagazynDokumentow
        # Magazyn tworzy katalog tylko gdy go nie ma; istniejący katalog bazy
        # nie jest zmieniany przez samo narzędzie.
        archive = MagazynDokumentow(self.gateway.data_root)
        path = archive.sciezka(row["sciezka_wzgledna"], row["sha256"])
        if name == "document.verify":
            return {"document_id": row["id"], "valid_sha256": True,
                    "size_bytes": row["rozmiar_bajtow"]}, [
                        self._evidence("document", str(row["id"]), call_id)]
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Dokument jest zbyt duży do automatycznej analizy")
        # Wywołujemy tylko istniejącą bezpieczną usługę OCR; ograniczamy
        # liczbę stron oraz ilość danych przekazywanych do modelu.
        from uslugi.odczyt_pdf import odczytaj_pdf
        method = args.get("method", "auto")
        found = odczytaj_pdf(path, z_ocr=method != "text", maks_stron=3)
        text = found.tekst_dla_llm[:20000]
        return {"document_id": row["id"], "text": text, "truncated": len(found.tekst_dla_llm) > 20000,
                "source_untrusted": True, "pages": len(found.strony)}, [
                    self._evidence("document", str(row["id"]), call_id)]

    def _expected(self, args: dict[str, Any], call_id: str):
        cycle = args["cycle"]
        now = self.task["context"].get("reference_date")
        if not now:
            raise ValueError("Brak dnia referencyjnego")
        date.fromisoformat(now)
        rows = self.db.execute(
            "SELECT o.id, o.profil_id, p.nazwa, p.dostawca, o.cykl, "
            "o.oczekiwany_od, o.wyjatek, o.powod_wyjatku, "
            "(SELECT COUNT(*) FROM powiazania_oczekiwanych l "
            " JOIN rachunki r ON r.id=l.rachunek_id "
            " WHERE l.oczekiwany_id=o.id AND r.wycofano_utc IS NULL) AS otrzymano "
            "FROM oczekiwane_dokumenty o JOIN profile_rachunkow p ON p.id=o.profil_id "
            "WHERE o.cykl=? AND p.aktywny=1 ORDER BY o.id LIMIT ?",
            (cycle,min(100,self.task["limits"]["max_records"])),
        ).fetchall()
        results=[]
        for r in rows:
            item=dict(r)
            if item["otrzymano"]:
                status="otrzymano"
            elif item["wyjatek"] == "nie_wystawiono":
                status="nie_wystawiono"
            elif item["wyjatek"] == "niepewne":
                status="niepewne"
            elif item["oczekiwany_od"] <= now:
                status="brak"
            else:
                status="oczekiwanie"
            item["status"]=status
            results.append(item)
        return {"cycle":cycle, "expected":results}, [
            self._evidence("profile",str(r["profil_id"]),call_id) for r in rows
        ]

    def _matches(self, args: dict[str, Any], call_id: str):
        invoice = self._get_invoice(args["invoice_id"])
        if invoice is None:
            raise LookupError("Nie znaleziono faktury")
        month = (invoice["okres_do"] or invoice["data_wystawienia"] or "")[:7]
        rows = self.db.execute(
            "SELECT o.id AS expected_id, o.profil_id, p.nazwa, p.dostawca, "
            "o.cykl, o.oczekiwany_od, "
            "CASE WHEN EXISTS(SELECT 1 FROM powiazania_oczekiwanych l "
            "WHERE l.oczekiwany_id=o.id AND l.rachunek_id=?) THEN 1 ELSE 0 END AS linked "
            "FROM oczekiwane_dokumenty o JOIN profile_rachunkow p ON p.id=o.profil_id "
            "WHERE o.cykl=? AND p.aktywny=1 ORDER BY linked DESC,o.id LIMIT ?",
            (invoice["id"],month,min(100,self.task["limits"]["max_records"])),
        ).fetchall()
        return {"invoice_id":invoice["id"],"cycle":month,
                "supplier":invoice["dostawca"],"candidates":[dict(r) for r in rows]}, [
            self._evidence("invoice",str(invoice["id"]),call_id)
        ]

    def trusted_evidence(self, finding: dict[str, Any]) -> bool:
        """Potwierdza wyłącznie wąski zbiór kodów mających dowód w wyniku narzędzia."""
        proof = finding.get("evidence", [])
        if len(proof) != 1:
            return False
        e = proof[0]
        record = self.results.get(e["tool_call_id"])
        if record is None or record["status"] != "ok" or e not in record["evidence"]:
            return False
        data = record["data"]
        if record["tool_name"] == "payment.inspect":
            if e["source_type"] != "invoice" or e["source_id"] != str(data["invoice_id"]):
                return False
            return {
                "INVOICE_OVERDUE": data["overdue"] is True,
                "INVOICE_UNPAID": data["status"] == "do_zaplaty",
                "INVOICE_PAID": data["status"] == "oplacony",
                "PAYMENT_DUE_SOON": data["due_soon_7_days"] is True,
            }.get(finding["code"], False)
        if record["tool_name"] == "cycle.evaluate":
            return (finding["code"] == "CYCLE_CLOSED"
                    and e["source_type"] == "cycle"
                    and e["source_id"] == data["cycle"]
                    and data["closed"] is True)
        return False
