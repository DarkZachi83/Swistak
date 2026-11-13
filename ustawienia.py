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


def load(path: Path | None = None) -> dict[str, str]:
    destination = Path(path) if path is not None else path_settings()
    try:
        data = json.loads(destination.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    language = data.get("language", "")
    model = data.get("ollama_model", "gemma3:4b")
    location = data.get("model_scan_dir", "")
    result = {
        "language": language if language in ("", "pl", "en") else "",
        "ollama_model": model if isinstance(model, str) and 0 < len(model.strip()) <= 120 else "gemma3:4b",
        "model_scan_dir": location if isinstance(location, str) and len(location) <= 2048
                          and not any(ord(c) < 32 for c in location) else "",
    }
    for key in SPECIALIST_KEYS:
        value = data.get(key, "")
        result[key] = (value.strip() if isinstance(value, str)
                       and len(value.strip()) <= 120
                       and not any(ord(c) < 32 for c in value) else "")
    return result


def save(prefs: dict[str, str], path: Path | None = None) -> None:
    dest = Path(path) if path is not None else path_settings()
    lang = prefs.get("language", "")
    model = prefs.get("ollama_model", "gemma3:4b").strip()
    location = prefs.get("model_scan_dir", "")
    specialist_values = {key: prefs.get(key, "") for key in SPECIALIST_KEYS}
    if (lang not in ("", "pl", "en") or not isinstance(model, str)
            or not model or len(model) > 120 or not isinstance(location, str)
            or len(location) > 2048 or any(ord(c) < 32 for c in location)
            or any(not isinstance(value, str) or len(value.strip()) > 120
                   or any(ord(char) < 32 for char in value)
                   for value in specialist_values.values())):
        raise ValueError("Invalid language, model or scan location")
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", dir=dest.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"language": lang, "ollama_model": model,
                       "model_scan_dir": location,
                       **{key: value.strip() for key, value in specialist_values.items()}},
                      handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dest)
        if os.name != "nt":
            os.chmod(dest, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
