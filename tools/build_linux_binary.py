# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Eksperymentalny, osobny pakiet PyInstaller --onedir dla Linux.

Nie publikuje GitHub Release; binaria pozostają artefaktem testów autora.
Nie skanuje katalogu danych użytkownika ani nie dołącza Tesseract/Ollama.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from wersja import __version__

ROOT = Path(__file__).resolve().parents[1]
APP = "Swistak"
ARCHIVE_ROOT = f"Swistak-Linux-{__version__}-bin"
ARCHIVE_NAME = f"swistak-linux-{__version__}-bin.tar.gz"
BINARY_DATA = (
    ("assets/branding/swistak-banner.jpeg", "assets/branding"),
    ("baza/schemat", "baza/schemat"),
    ("i18n/pl.json", "i18n"),
    ("i18n/en.json", "i18n"),
)
PUBLIC_NOTICES = ("LICENSE", "NOTICE.md", "THIRD_PARTY_LICENSES.md")
INSTALLED_PACKAGES = (
    "PySide6", "PySide6-Essentials", "PySide6-Addons",
    "shiboken6", "pypdfium2", "pypdfium2_raw",
    "Pillow", "pdfplumber", "pdfminer.six", "pytesseract",
)


def _file(path: str) -> Path:
    result = (ROOT / path).resolve()
    if not result.is_file() or not result.is_relative_to(ROOT.resolve()):
        raise FileNotFoundError(f"Brak pliku wymaganego do wydania: {path}")
    return result


def pyinstaller_command(output: Path, work: Path, spec: Path) -> list[str]:
    """Polecenie przygotowane do testu bez uruchamiania PyInstaller."""
    if sys.platform != "linux":
        raise RuntimeError("Pakiet binarny Linux trzeba budować na Linuxie.")
    files = []
    for name, location in BINARY_DATA:
        source = ROOT / name
        if not source.exists():
            raise FileNotFoundError(source)
        files.extend(("--add-data", f"{source.resolve()}:{location}"))
    return [
        sys.executable, "-m", "PyInstaller",
        "--onedir", "--console", "--noconfirm", "--clean", "--noupx",
        "--name", APP,
        "--contents-directory", "_internal",
        "--distpath", str(output.resolve()),
        "--workpath", str(work.resolve()),
        "--specpath", str(spec.resolve()),
        "--hidden-import=PySide6.QtPdf",
        "--collect-all=pypdfium2_raw",
        "--collect-data=pypdfium2",
        *files,
        str(_file("main.py")),
    ]


def _is_license_path(relative: Path) -> bool:
    parts = [item.lower() for item in relative.parts]
    basename = parts[-1] if parts else ""
    return (
        any(part in ("licenses", "licences", "build_licenses") for part in parts)
        or basename.startswith(("license.", "license-", "licence.", "copying.", "notice."))
        or basename in ("license", "copying", "notice", "copyright")
    )


def collect_installed_notices(bundle: Path) -> list[str]:
    """Kopie informacji licencyjnych z rzeczywiście użytych kół Pythona.

    Pliki znajdujemy przez importlib.metadata; nie zgadujemy ścieżek w wheel.
    Żaden wygenerowany manifest nie stanowi certyfikatu zgodności prawnej.
    """
    target = bundle / "licencje-zaleznosci"
    target.mkdir(parents=True, exist_ok=True)
    records = ["Świstak binary QA — wykaz deklaracji i tekstów licencji",
               "WYMAGA RĘCZNEGO PRZEGLĄDU PRZED PUBLICZNĄ DYSTRYBUCJĄ.", ""]
    for name in INSTALLED_PACKAGES:
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            records.append(f"{name}: NIE ZNALEZIONO dystrybucji w środowisku budowania")
            continue
        version = distribution.version
        records.append(f"{name} {version}:")
        seen = 0
        for relative in distribution.files or ():
            path = Path(str(relative))
            if not _is_license_path(path):
                continue
            source = Path(distribution.locate_file(relative))
            if not source.is_file() or source.is_symlink():
                continue
            if source.stat().st_size > 5_000_000:
                records.append(f"  POMINIĘTO >5MB: {relative}")
                continue
            # Zacznij od nazwy pakietu i zachowaj strukturę pliku w wheel.
            destination = target / name.replace("/", "_") / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            records.append(f"  {destination.relative_to(bundle).as_posix()}")
            seen += 1
        if not seen:
            records.append("  UWAGA: nie znaleziono plików licencyjnych w metadanych wheel")
    records.extend([
        "",
        "Obowiązki LGPL Qt i licencje binarne PDFium wymagają ręcznej kontroli.",
        "Zobacz docs/LINUX_BINARY_BETA.md i THIRD_PARTY_LICENSES.md.",
    ])
    (bundle / "INWENTARYZACJA_LICENCJI.txt").write_text(
        "\n".join(records) + "\n", encoding="utf-8"
    )
    return records


def package_bundle(folder: Path, output: Path) -> Path:
    """Archiwizuje tylko ustalony katalog, nie odczytuje katalogu danych."""
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ARCHIVE_NAME
    with tarfile.open(archive, "w:gz", dereference=False) as tar:
        tar.add(folder, arcname=ARCHIVE_ROOT, recursive=True)
    return archive


def build(output: Path, work: Path, spec: Path) -> Path:
    output = output.resolve()
    work = work.resolve()
    spec = spec.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    spec.mkdir(parents=True, exist_ok=True)
    cmd = pyinstaller_command(output, work, spec)
    subprocess.run(cmd, cwd=ROOT, check=True)
    bundle = output / APP
    binary = bundle / APP
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(f"Nie znaleziono binarnego programu: {binary}")

    start = _file("packaging/linux-binary/start.sh")
    shutil.copy2(start, bundle / "start.sh")
    (bundle / "start.sh").chmod(0o755)
    (bundle / "VERSION").write_text(__version__ + "\n", encoding="utf-8")
    for path in PUBLIC_NOTICES:
        shutil.copy2(_file(path), bundle / path)
    shutil.copy2(_file("docs/LINUX_BINARY_BETA.md"), bundle / "INSTRUKCJA_TESTOW.md")
    collect_installed_notices(bundle)

    archive = package_bundle(bundle, output)
    print(f"Świstak Linux binary QA: {archive} ({archive.stat().st_size} B)")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Testowa binarna Beta Linux Świstaka")
    parser.add_argument("--output", type=Path, default=Path("dist") / "binary")
    parser.add_argument("--work", type=Path, default=Path("build") / "pyinstaller")
    parser.add_argument("--spec", type=Path, default=Path("build") / "spec")
    args = parser.parse_args()
    build(args.output, args.work, args.spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
