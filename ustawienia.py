# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Konfiguracja widoku oddzielona od SQLite i archiwum rachunków."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SPECIALIST_ROLES = ("extractor", "verifier", "financial_analyst", "cycle_analyst")
SPECIALIST_KEYS = tuple("model_" + role for role in SPECIALIST_ROLES)
DEFAULTS = {
    "language": "", "ollama_model": "gemma3:4b", "model_scan_dir": "",
    **{key: "" for key in SPECIALIST_KEYS},
}


def modele_specjalistyczne(prefs: dict[str, str]) -> dict[str, str]:
    """Zwróć tylko świadomie skonfigurowane, lokalne role."""
    return {role: prefs.get("model_" + role, "").strip()
            for role in SPECIALIST_ROLES if prefs.get("model_" + role, "").strip()}



def path_settings() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return root / "Swistak" / "settings.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Swistak" / "settings.json"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "swistak" / "settings.json"


def _normalizuj_wartosc(key: str, value: str) -> str:
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise ValueError(f"Nieprawidłowe ustawienie: {key}")
    if key == "language":
        if value not in ("", "pl", "en"):
            raise ValueError("Nieprawidłowy język")
        return value
    if key == "model_scan_dir":
        if len(value) > 2048:
            raise ValueError("Za długa ścieżka katalogu modeli")
        return value
    model = value.strip()
    if len(model) > 120 or (key == "ollama_model" and not model):
        raise ValueError(f"Nieprawidłowa nazwa modelu: {key}")
    return model


def waliduj(prefs: dict) -> dict[str, str]:
    """Waliduj znane klucze. Zachowaj różnicę między brakiem a pustą wartością."""
    if not isinstance(prefs, dict):
        raise ValueError("Nieprawidłowy format ustawień")
    return {key: _normalizuj_wartosc(key, prefs[key]) for key in DEFAULTS if key in prefs}


def load(path: Path | None = None) -> dict[str, str]:
    destination = Path(path) if path is not None else path_settings()
    try:
        data = json.loads(destination.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return DEFAULTS.copy()
    result = DEFAULTS.copy()
    if isinstance(data, dict):
        for key in result:
            if key in data:
                try:
                    result[key] = _normalizuj_wartosc(key, data[key])
                except ValueError:
                    pass  # Jedna uszkodzona wartość nie kasuje pozostałych.
    return result


def save(prefs: dict[str, str], path: Path | None = None) -> None:
    dest = Path(path) if path is not None else path_settings()
    data = {**DEFAULTS, **waliduj(prefs)}
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", dir=dest.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dest)
        if os.name != "nt":
            os.chmod(dest, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
