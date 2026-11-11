# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Prywatne, zatwierdzane przez użytkownika wzorce faktur — JSON v1.

Nie zapisuje PDF, surowego OCR ani wartości historycznych faktur. Istniejące
migracje SQLite nie są modyfikowane. Zmiany mają wersje i bezpieczny zapis.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
ID_RE = re.compile(r"^wz-[0-9a-f]{32}$")
POLA_WZORCA = frozenset((
    "dostawca", "numer_faktury", "kwota_do_zaplaty", "waluta",
    "data_wystawienia", "termin_platnosci", "okres_od", "okres_do",
    "numer_konta_bankowego", "kategoria_sugerowana",
))
KLUCZE = frozenset((
    "schema_version", "template_id", "revision", "name", "status",
    "identification", "category", "fields", "agent_notes", "approved_utc",
))
FORMATY = frozenset(("DD.MM.RRRR", "RRRR-MM-DD", "MM/RRRR", "PLN", "NRB_OR_IBAN", ""))
UWAGA_NR_KONTA = re.compile(r"(?<!\d)(?:\d[ \t-]?){26}(?!\d)")
MAX_JSON = 80_000


def _tekst(value: object, limit: int, label: str, *, pusty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}: wymagany tekst")
    value = " ".join(value.split())
    if len(value) > limit or (not pusty and not value):
        raise ValueError(f"{label}: niedozwolona długość")
    if UWAGA_NR_KONTA.search(value):
        raise ValueError(f"{label}: nie zapisuj numerów kont bankowych we wzorcu")
    return value


def _lista(value: object, max_count: int, limit: int, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > max_count:
        raise ValueError(f"{label}: nieprawidłowa lista")
    values = [_tekst(item, limit, label, pusty=False) for item in value]
    return list(dict.fromkeys(values))


def zatwierdz_strukture(document: dict) -> dict:
    """Biała lista kluczy; nie wolno przemycać danych nabywcy lub rachunku."""
    if not isinstance(document, dict) or set(document) != KLUCZE:
        raise ValueError("Nieprawidłowy zestaw kluczy wzorca")
    data = copy.deepcopy(document)
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Nieobsługiwana wersja formatu wzorca")
    if not isinstance(data["template_id"], str) or not ID_RE.fullmatch(data["template_id"]):
        raise ValueError("Nieprawidłowy identyfikator wzorca")
    if type(data["revision"]) is not int or data["revision"] < 1:
        raise ValueError("Nieprawidłowa rewizja")
    if data["status"] not in ("approved", "inactive"):
        raise ValueError("Nieprawidłowy status wzorca")
    data["name"] = _tekst(data["name"], 120, "Nazwa wzorca", pusty=False)
    data["category"] = (
        _tekst(data["category"], 80, "Kategoria") if data["category"] is not None else None
    )
    ident = data["identification"]
    if not isinstance(ident, dict) or set(ident) != {
        "seller_nip", "seller_aliases", "layout_labels",
    }:
        raise ValueError("Nieprawidłowe dane identyfikacyjne")
    nip = ident["seller_nip"]
    if nip is not None and (not isinstance(nip, str) or not re.fullmatch(r"\d{10}", nip)):
        raise ValueError("NIP sprzedawcy musi mieć 10 cyfr")
    ident["seller_aliases"] = _lista(ident["seller_aliases"], 12, 120, "Aliasy sprzedawcy")
    ident["layout_labels"] = _lista(ident["layout_labels"], 20, 80, "Etykiety układu")
    if nip is None and not ident["seller_aliases"]:
        raise ValueError("Wzorzec wymaga NIP lub nazwy sprzedawcy")
    fields = data["fields"]
    if not isinstance(fields, dict) or not set(fields).issubset(POLA_WZORCA):
        raise ValueError("Wzorzec zawiera niedozwolone pole")
    for field, config in fields.items():
        if not isinstance(config, dict) or set(config) != {
            "find_by", "source_format", "target_format", "note",
        }:
            raise ValueError(f"Nieprawidłowe reguły pola {field}")
        config["find_by"] = _lista(config["find_by"], 8, 80, field)
        for part in ("source_format", "target_format"):
            if config[part] not in FORMATY:
                raise ValueError(f"Nieznany format w polu {field}")
        config["note"] = _tekst(config["note"], 450, "Wskazówka pola")
    data["agent_notes"] = _lista(data["agent_notes"], 12, 450, "Wskazówki dla agenta")
    approved = data["approved_utc"]
    if not isinstance(approved, str) or len(approved) > 40:
        raise ValueError("Nieprawidłowa data akceptacji")
    try:
        datetime.fromisoformat(approved.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Nieprawidłowa data akceptacji") from exc
    if len(json.dumps(data, ensure_ascii=False)) > MAX_JSON:
        raise ValueError("Wzorzec przekracza limit rozmiaru")
    return data


def _teraz() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def nowy_wzorzec(name: str, identification: dict, category: str | None = None,
                 fields: dict | None = None, agent_notes: list[str] | None = None) -> dict:
    document = {
        "schema_version": SCHEMA_VERSION,
        "template_id": "wz-" + uuid.uuid4().hex,
        "revision": 1, "name": name, "status": "approved",
        "identification": identification,
        "category": category, "fields": fields or {},
        "agent_notes": agent_notes or [], "approved_utc": _teraz(),
    }
    return zatwierdz_strukture(document)


class MagazynWzorcow:
    def __init__(self, katalog_danych: Path):
        # Katalog jest zawsze w lokalnej przestrzeni użytkownika, nie repo.
        self.katalog = Path(katalog_danych).expanduser().resolve() / "wzorce"

    def _path(self, template_id: str) -> Path:
        if not isinstance(template_id, str) or not ID_RE.fullmatch(template_id):
            raise ValueError("Niedozwolony identyfikator wzorca")
        return self.katalog / (template_id + ".json")

    def _read(self, path: Path) -> dict:
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError("Nie znaleziono bezpiecznego pliku wzorca")
        if path.stat().st_size > MAX_JSON:
            raise ValueError("Zbyt duży plik wzorca")
        return zatwierdz_strukture(json.loads(path.read_text(encoding="utf-8")))

    def pobierz(self, template_id: str) -> dict:
        data = self._read(self._path(template_id))
        if data["template_id"] != template_id:
            raise ValueError("Identyfikator w pliku nie zgadza się z nazwą")
        return data

    def lista(self, *, tylko_aktywne: bool = False) -> list[dict]:
        if not self.katalog.is_dir():
            return []
        templates = []
        for path in sorted(self.katalog.glob("wz-*.json")):
            if path.is_symlink():
                continue
            data = self._read(path)  # uszkodzony JSON musi być widocznym błędem
            if data["template_id"] != path.stem:
                raise ValueError("Niespójny identyfikator pliku wzorca")
            if not tylko_aktywne or data["status"] == "approved":
                templates.append(data)
        return templates

    def _write(self, path: Path, data: dict) -> None:
        if path.is_symlink():
            raise ValueError("Niedozwolony link symboliczny")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        if len(raw) > MAX_JSON:
            raise ValueError("Zbyt duży wzorzec")
        fd, tmp = tempfile.mkstemp(prefix=".wz-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as file:
                os.fchmod(file.fileno(), 0o600)
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def utworz(self, proposed: dict) -> dict:
        data = zatwierdz_strukture(proposed)
        if data["revision"] != 1:
            raise ValueError("Nowy wzorzec musi mieć rewizję 1")
        path = self._path(data["template_id"])
        self.katalog.mkdir(parents=True, exist_ok=True, mode=0o700)
        # O_EXCL — nie nadpisuj istniejącego wzorca tym samym ID.
        if path.exists() or path.is_symlink():
            raise FileExistsError("Wzorzec już istnieje")
        # Operacja lokalna, pojedynczy interfejs; ewentualny błąd zapisu jest jawny.
        self._write(path, data)
        return data

    def aktualizuj(self, template_id: str, proposed: dict, *, expected_revision: int) -> dict:
        old = self.pobierz(template_id)
        if old["revision"] != expected_revision:
            raise ValueError("Wzorzec został zmieniony; odśwież dane przed zapisem")
        data = zatwierdz_strukture({
            **copy.deepcopy(proposed),
            "schema_version": SCHEMA_VERSION,
            "template_id": template_id,
            "revision": old["revision"] + 1,
            "approved_utc": _teraz(),
        })
        archive = self.katalog / "historia" / f"{template_id}.rev-{old['revision']:06d}.json"
        if archive.exists() or archive.is_symlink():
            raise ValueError("Rewizja historyczna już istnieje — zatrzymano aktualizację")
        self._write(archive, old)
        self._write(self._path(template_id), data)
        return data

    def dezaktywuj(self, template_id: str, *, expected_revision: int) -> dict:
        data = self.pobierz(template_id)
        data["status"] = "inactive"
        return self.aktualizuj(template_id, data, expected_revision=expected_revision)

    def przywroc(self, template_id: str, revision: int, *, expected_revision: int) -> dict:
        if type(revision) is not int or revision < 1:
            raise ValueError("Nieprawidłowa rewizja historyczna")
        path = self.katalog / "historia" / f"{self._path(template_id).stem}.rev-{revision:06d}.json"
        historic = self._read(path)
        if historic["template_id"] != template_id or historic["revision"] != revision:
            raise ValueError("Nieprawidłowy historyczny wzorzec")
        return self.aktualizuj(template_id, historic, expected_revision=expected_revision)
