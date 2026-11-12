# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Prywatne, pełne kopie Świstaka: SQLite + PDF + wzorce + ustawienia.

Jedno archiwum ZIP ze sprawdzanym manifestem SHA-256. Nigdy nie wykonujemy
skryptów ani nie wypakowujemy niesprawdzonych ścieżek z archiwum.
Dane rzeczywiste pozostają na komputerze użytkownika.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from uslugi.rachunki import RejestrRachunkow

FORMAT = "swistak-backup"
WERSJA = 1
_MANIFEST = "manifest.json"
_SQLITE = "swistak.sqlite3"
_PREFS = "config/settings.json"
_KATALOGI = ("dokumenty", "wzorce", "kopie_migracji")
_BLOK = 1024 * 1024
_MAX_FILES = 50000
_MAX_SIZE = 100 * 1024**3
_MAX_MANIFEST = 8 * 1024**2
_HASH = re.compile(r"[a-f0-9]{64}\Z")


class BladKopii(RuntimeError):
    """Niespójny backup, brak dostępu albo niebezpieczne przywracanie."""


@dataclass(frozen=True)
class OpisKopii:
    utworzona_utc: str
    pliki: int
    dokumenty_pdf: int
    wzorce_json: int
    bajty: int
    ustawienia: bool


@dataclass
class PrzygotowanePrzywracanie:
    katalog_roboczy: Path
    katalog_danych: Path
    ustawienia: dict[str, str] | None
    opis: OpisKopii

    def sprzataj(self) -> None:
        shutil.rmtree(self.katalog_roboczy, ignore_errors=True)


def _bezpieczna_nazwa(name: str) -> bool:
    if not isinstance(name, str) or "\\" in name or "\0" in name:
        return False
    path = PurePosixPath(name)
    if (not name or name.startswith("/") or name.endswith("/")
            or "//" in name or str(path) != name
            or any(p in (".", "..") or ":" in p for p in path.parts)):
        return False
    if name in (_SQLITE, _PREFS):
        return True
    if len(path.parts) < 2 or path.parts[0] not in _KATALOGI:
        return False
    # W archiwum trafiają tylko dokumenty, wzorce i wcześniejsze snapshoty.
    return (
        (path.parts[0] == "dokumenty" and path.suffix.lower() == ".pdf")
        or (path.parts[0] == "wzorce" and path.suffix.lower() == ".json")
        or (path.parts[0] == "kopie_migracji" and path.suffix.lower() == ".sqlite3")
    )


def _sprawdz_zwykly_plik(path: Path) -> None:
    """Nie podążaj za linkami — archiwum nie może wyciec poza katalog danych."""
    if path.is_symlink() or not path.is_file():
        raise BladKopii(f"Niedozwolony plik lub dowiązanie: {path}")
    for parent in path.parents:
        if parent.is_symlink():
            raise BladKopii(f"Niedozwolony katalog będący dowiązaniem: {parent}")


def _pliki_danych(root: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for directory in _KATALOGI:
        folder = root / directory
        if folder.is_symlink():
            raise BladKopii(f"Dowiązanie w danych: {folder}")
        if not folder.exists():
            continue
        if not folder.is_dir():
            raise BladKopii(f"Nieprawidłowy katalog danych: {folder}")
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise BladKopii(f"Dowiązanie w archiwum danych: {path}")
            if path.is_dir():
                continue
            _sprawdz_zwykly_plik(path)
            rel = path.relative_to(root).as_posix()
            if not _bezpieczna_nazwa(rel):
                raise BladKopii(f"Nieznany typ pliku w katalogu danych: {rel}")
            found.append((rel, path))
            if len(found) > _MAX_FILES:
                raise BladKopii("Zbyt wiele plików w katalogu danych")
    return found


def _hash_i_zapis(source: Path, zipf: zipfile.ZipFile, name: str) -> dict:
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as handle, zipf.open(name, "w", force_zip64=True) as dest:
        while chunk := handle.read(_BLOK):
            size += len(chunk)
            if size > _MAX_SIZE:
                raise BladKopii("Zbyt duży plik")
            digest.update(chunk)
            dest.write(chunk)
    return {"path": name, "size": size, "sha256": digest.hexdigest()}


def _zapis_snapshot_sqlite(db: sqlite3.Connection, path: Path) -> None:
    snapshot = sqlite3.connect(path)
    try:
        db.backup(snapshot)  # Spójne nawet przy otwartym połączeniu Świstaka.
        if snapshot.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise BladKopii("SQLite nie przeszła kontroli integralności")
        if snapshot.execute("PRAGMA foreign_key_check").fetchall():
            raise BladKopii("SQLite ma niespójne klucze obce")
    finally:
        snapshot.close()


def utworz_kopie(
    rejestr: RejestrRachunkow, cel: str | Path, *,
    ustawienia: Path | None = None,
) -> OpisKopii:
    """Utwórz kompletny backup. Istniejący plik nigdy nie jest nadpisywany."""
    root = rejestr.katalog
    destination = Path(cel).expanduser().absolute()
    actual_destination = destination.resolve(strict=False)
    config = Path(ustawienia) if ustawienia is not None else None
    if not destination.name.lower().endswith(".zip"):
        raise BladKopii("Wybierz nazwę kopii z rozszerzeniem .zip")
    if actual_destination == root or root in actual_destination.parents:
        raise BladKopii("Kopię trzeba zapisać poza katalogiem danych Świstaka")
    if destination.exists() or destination.is_symlink():
        raise BladKopii("Kopia o tej nazwie już istnieje. Wybierz inną nazwę")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    files = _pliki_danych(root)
    with tempfile.TemporaryDirectory(prefix=".swistak-kopia-", dir=destination.parent) as work:
        temp = Path(work)
        snap = temp / _SQLITE
        _zapis_snapshot_sqlite(rejestr.db, snap)
        sources: list[tuple[str, Path]] = [(_SQLITE, snap), *files]
        if config is not None and config.is_file():
            _sprawdz_zwykly_plik(config)
            sources.append((_PREFS, config))
        metadata: list[dict] = []
        total = 0
        archive = temp / "kopia.zip"
        created_destination = False
        try:
            with zipfile.ZipFile(
                archive, "w", compression=zipfile.ZIP_DEFLATED,
                compresslevel=6, allowZip64=True,
            ) as zipf:
                for name, path in sources:
                    entry = _hash_i_zapis(path, zipf, name)
                    total += entry["size"]
                    if total > _MAX_SIZE:
                        raise BladKopii("Kopia przekracza limit 100 GiB")
                    metadata.append(entry)
                # Upewnij się, że każdy PDF powiązany z bazą jest w kopii.
                _sprawdz_powiazania(snap, metadata)
                created = datetime.now(timezone.utc).isoformat(timespec="seconds")
                manifest = {"format": FORMAT, "version": WERSJA,
                            "created_utc": created, "files": metadata}
                zipf.writestr(
                    _MANIFEST, json.dumps(manifest, ensure_ascii=False,
                                          separators=(",", ":")).encode("utf-8")
                )
            # Nie zamieniamy istniejących plików; na tym samym dysku link jest atomowy.
            try:
                os.link(archive, destination)
                created_destination = True
            except FileExistsError as exc:
                raise BladKopii("Plik kopii już istnieje") from exc
            except OSError:
                # Dyski bez hardlinków: tworzenie O_EXCL bez nadpisania cudzej kopii.
                try:
                    with destination.open("xb") as target:
                        created_destination = True
                        with archive.open("rb") as source:
                            shutil.copyfileobj(source, target, _BLOK)
                        target.flush()
                        os.fsync(target.fileno())
                except BaseException as exc:
                    raise BladKopii(f"Nie udało się zapisać kopii: {exc}") from exc
            if os.name != "nt":
                os.chmod(destination, 0o600)
            return OpisKopii(
                utworzona_utc=created, pliki=len(metadata),
                dokumenty_pdf=sum(x["path"].startswith("dokumenty/") for x in metadata),
                wzorce_json=sum(x["path"].startswith("wzorce/") for x in metadata),
                bajty=total, ustawienia=any(x["path"] == _PREFS for x in metadata),
            )
        except BaseException:
            # Nie pozostawiaj uszkodzonej kopii (bez usuwania starszych kopii).
            if created_destination:
                destination.unlink(missing_ok=True)
            raise


def _wybierz_opis(files: list[dict], created: str) -> OpisKopii:
    return OpisKopii(
        utworzona_utc=created, pliki=len(files),
        dokumenty_pdf=sum(x["path"].startswith("dokumenty/") for x in files),
        wzorce_json=sum(x["path"].startswith("wzorce/") for x in files),
        bajty=sum(x["size"] for x in files),
        ustawienia=any(x["path"] == _PREFS for x in files),
    )


def _wczytaj_manifest(zipf: zipfile.ZipFile) -> tuple[list[dict], OpisKopii]:
    entries = zipf.infolist()
    names = [entry.filename for entry in entries]
    if not 2 <= len(names) <= _MAX_FILES + 2 or len(set(names)) != len(names):
        raise BladKopii("Nieprawidłowa liczba plików lub powielone nazwy")
    if _MANIFEST not in names:
        raise BladKopii("Brak manifestu kopii")
    manifest_info = zipf.getinfo(_MANIFEST)
    if manifest_info.file_size > _MAX_MANIFEST:
        raise BladKopii("Manifest kopii jest za duży")
    try:
        manifest = json.loads(zipf.read(_MANIFEST))
    except (UnicodeError, ValueError) as exc:
        raise BladKopii("Niepoprawny manifest JSON") from exc
    if (not isinstance(manifest, dict) or manifest.get("format") != FORMAT
            or manifest.get("version") != WERSJA
            or not isinstance(manifest.get("created_utc"), str)
            or not isinstance(manifest.get("files"), list)):
        raise BladKopii("Nieobsługiwany format kopii Świstaka")
    files = manifest["files"]
    expected: set[str] = {_MANIFEST}
    total = 0
    if len(files) > _MAX_FILES:
        raise BladKopii("Zbyt wiele plików w kopii")
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise BladKopii("Nieprawidłowy element manifestu")
        name, size, sha = item["path"], item["size"], item["sha256"]
        if (not _bezpieczna_nazwa(name) or name in expected
                or type(size) is not int or not 0 <= size <= _MAX_SIZE
                or not isinstance(sha, str) or not _HASH.fullmatch(sha)):
            raise BladKopii("Niebezpieczna nazwa pliku lub niepoprawny SHA-256")
        expected.add(name)
        total += size
        if total > _MAX_SIZE:
            raise BladKopii("Kopia przekracza limit 100 GiB")
    if _SQLITE not in expected or expected != set(names):
        raise BladKopii("Lista ZIP różni się od manifestu")
    by_name = {item["path"]: item["size"] for item in files}
    for entry in entries:
        if entry.is_dir():
            raise BladKopii("Kopia zawiera nieoczekiwany katalog")
        if (entry.filename != _MANIFEST
                and entry.file_size != by_name[entry.filename]):
            raise BladKopii("Rozmiar pliku różni się od manifestu")
        # Blokuj symlinki i nietypowe typy plików z innych systemów.
        mode = (entry.external_attr >> 16) & 0o170000
        if mode not in (0, stat.S_IFREG):
            raise BladKopii("Kopia zawiera niedozwolony typ pliku")
    return files, _wybierz_opis(files, manifest["created_utc"])


def _sprawdz_powiazania(baza: Path, files: list[dict]) -> None:
    """Integralność SQLite i dowód zgodności każdego PDF z bazą."""
    db = sqlite3.connect(baza)
    try:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise BladKopii("Uszkodzona baza SQLite w kopii")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise BladKopii("Baza w kopii ma błędne klucze obce")
        by_name = {x["path"]: x["sha256"] for x in files}
        for name, sha in db.execute("SELECT sciezka_wzgledna, sha256 FROM dokumenty"):
            if (not isinstance(name, str) or not _bezpieczna_nazwa(name)
                    or not name.startswith("dokumenty/") or by_name.get(name) != sha):
                raise BladKopii("Baza wskazuje brakujący lub zmieniony PDF")
    except sqlite3.DatabaseError as exc:
        raise BladKopii(f"Nie można sprawdzić bazy kopii: {exc}") from exc
    finally:
        db.close()


def _sprawdz_dane(folder: Path, files: list[dict]) -> None:
    _sprawdz_powiazania(folder / _SQLITE, files)


def przygotuj_przywracanie(
    archive: str | Path, root: str | Path,
) -> PrzygotowanePrzywracanie:
    """Sprawdź całe archiwum PRZED dotknięciem istniejących danych.

    Wszystkie ścieżki docelowe konstruuje aplikacja z zaakceptowanego manifestu.
    Katalog tymczasowy jest obok danych, aby późniejsze podmiany były atomowe.
    """
    original = Path(root).expanduser().absolute()
    if original.is_symlink() or not original.is_dir():
        raise BladKopii("Nieprawidłowy katalog danych aplikacji")
    path = Path(archive).expanduser().absolute()
    if not path.is_file() or path.is_symlink():
        raise BladKopii("Nie znaleziono zwykłego pliku ZIP")
    work = Path(tempfile.mkdtemp(prefix=".swistak-przywroc-", dir=original.parent))
    prepared = work / "data"
    prepared.mkdir(mode=0o700)
    try:
        with zipfile.ZipFile(path, "r") as zipf:
            files, opis = _wczytaj_manifest(zipf)
            for item in files:
                relative = item["path"]
                target = work / relative if relative == _PREFS else prepared / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                digest = hashlib.sha256()
                size = 0
                with zipf.open(relative, "r") as source, target.open("xb") as dest:
                    while chunk := source.read(_BLOK):
                        size += len(chunk)
                        if size > item["size"]:
                            raise BladKopii("Wykryto przekroczenie rozmiaru pliku")
                        digest.update(chunk)
                        dest.write(chunk)
                    dest.flush()
                    os.fsync(dest.fileno())
                if size != item["size"] or digest.hexdigest() != item["sha256"]:
                    raise BladKopii("Kontrola SHA-256 kopii nie powiodła się")
                if os.name != "nt":
                    target.chmod(0o600)
        _sprawdz_dane(prepared, files)
        prefs = None
        if opis.ustawienia:
            try:
                data = json.loads((work / _PREFS).read_text(encoding="utf-8"))
                if (not isinstance(data, dict) or
                        data.get("language") not in ("", "pl", "en")
                        or not isinstance(data.get("ollama_model"), str)
                        or not 0 < len(data["ollama_model"].strip()) <= 120):
                    raise ValueError("Nieprawidłowe ustawienia")
                prefs = {"language": data["language"],
                         "ollama_model": data["ollama_model"]}
            except (OSError, UnicodeError, ValueError) as exc:
                raise BladKopii("Ustawienia z kopii są uszkodzone") from exc
        return PrzygotowanePrzywracanie(work, prepared, prefs, opis)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


def podmien_dane(kopia: PrzygotowanePrzywracanie, root: Path) -> Path:
    """Wymaga zamknięcia bieżącej bazy i PDF. Oryginał zachowany obok katalogu."""
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir() or not kopia.katalog_danych.is_dir():
        raise BladKopii("Nie można podmienić katalogu danych")
    previous = root.with_name(
        root.name + "-przed-przywroceniem-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-" + uuid.uuid4().hex[:8]
    )
    os.replace(root, previous)
    try:
        os.replace(kopia.katalog_danych, root)
    except BaseException:
        os.replace(previous, root)
        raise
    return previous


def cofnij_podmiane(root: Path, poprzedni: Path) -> None:
    """Przy błędzie uruchomienia odtwórz poprzedni katalog, nie usuwając danych."""
    root = Path(root).absolute()
    if not poprzedni.is_dir():
        raise BladKopii("Brak oryginalnego katalogu do wycofania operacji")
    failed = root.with_name(root.name + "-nieudane-przywracanie-" + uuid.uuid4().hex[:8])
    if root.exists():
        os.replace(root, failed)
    os.replace(poprzedni, root)
