# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Minimalny pakiet źródłowy Linux Beta, bez kodu i danych prywatnych użytkownika.

Nie bundluje Qt, PDFium, Tesseract ani modelu Ollama.
"""
from __future__ import annotations

import argparse
import gzip
import io
import tarfile
from pathlib import Path

from wersja import __version__

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = f"Swistak-Linux-{__version__}"
ARCHIVE_NAME = f"swistak-linux-{__version__}-source.tar.gz"

# Jawne allowlisty: nie dodawaj .venv, plików PDF, baz, kopii itd.
ROOT_FILES = (
    "main.py", "wersja.py", "ustawienia.py", "konfiguracja.py",
    "uruchom.sh", "requirements.txt", "README.md", "LICENSE",
    "NOTICE.md", "THIRD_PARTY_LICENSES.md",
    "licencje/rejestr.json", "assets/branding/swistak-banner.jpeg",
    "docs/LINUX_BETA.md", "docs/LICENCJONOWANIE.md",
    "docs/ai_core/contracts_v1.schema.json", "docs/ai_core/tools_v1.json",
)
DIRECTORIES = {
    "ai_core": frozenset({".py"}),
    "baza": frozenset({".py", ".sql"}),
    "gui": frozenset({".py"}),
    "uslugi": frozenset({".py"}),
    "i18n": frozenset({".py", ".json"}),
}
PACKAGE_SCRIPTS = {
    "instaluj.sh": "packaging/linux/instaluj.sh",
    "start.sh": "packaging/linux/start.sh",
}


def _source(path: str) -> Path:
    file = ROOT / path
    if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(ROOT.resolve()):
        raise FileNotFoundError(f"Brak lub niebezpieczny zasób do pakietu: {path}")
    return file


def manifest() -> dict[str, Path]:
    files: dict[str, Path] = {}
    for filename in ROOT_FILES:
        files[filename] = _source(filename)
    for directory, extensions in DIRECTORIES.items():
        source = ROOT / directory
        if not source.is_dir():
            raise FileNotFoundError(f"Nie ma katalogu: {source}")
        for file in sorted(source.rglob("*")):
            if file.is_symlink():
                raise ValueError(f"Niedozwolony symlink: {file}")
            if file.is_file() and file.suffix in extensions:
                rel = file.relative_to(ROOT).as_posix()
                files[rel] = _source(rel)
    if not any(f.startswith("baza/schemat/") and f.endswith(".sql") for f in files):
        raise FileNotFoundError("Brak migracji SQL; pakiet nie może działać.")
    if not {"i18n/pl.json", "i18n/en.json"}.issubset(files):
        raise FileNotFoundError("Brak polskich lub angielskich tłumaczeń.")
    # AI Core 1.0 używa schematów odczytywanych z dysku w czasie pracy.
    # Brak któregokolwiek elementu oznacza paczkę niezdolną do analizy.
    mandatory_ai = {
        "ai_core/contracts.py", "ai_core/gateway.py", "ai_core/ollama.py",
        "ai_core/hybrid.py", "ai_core/router.py", "ai_core/orchestrator.py",
        "docs/ai_core/contracts_v1.schema.json",
        "docs/ai_core/tools_v1.json",
    }
    if not mandatory_ai.issubset(files):
        raise FileNotFoundError("Brak plików runtime AI Core w pakiecie.")
    for target, original in PACKAGE_SCRIPTS.items():
        files[target] = _source(original)
    return files


def build(output_dir: Path) -> Path:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / ARCHIVE_NAME
    contents = manifest()
    # Archiwum jest deterministyczne: stała kolejność, mtime, właściciel, prawa.
    with output_file.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for name in sorted(contents):
                    data = contents[name].read_bytes()
                    info = tarfile.TarInfo(f"{ARCHIVE_ROOT}/{name}")
                    info.size = len(data)
                    info.mode = 0o755 if name in ("start.sh", "instaluj.sh", "uruchom.sh") else 0o644
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    tar.addfile(info, io.BytesIO(data))
    return output_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Zbuduj źródłowe archiwum Świstak Linux Beta")
    parser.add_argument("--output", default="dist", type=Path, help="Katalog na archiwum")
    args = parser.parse_args()
    result = build(args.output)
    print(f"Świstak Linux Beta: {result} ({result.stat().st_size} bajtów)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
