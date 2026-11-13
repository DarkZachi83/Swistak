# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Konfiguracja widoku oddzielona od SQLite i archiwum rachunków."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

DEFAULTS = {"language": "", "ollama_model": "gemma3:4b", "model_scan_dir": ""}


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
    return {
        "language": language if language in ("", "pl", "en") else "",
        "ollama_model": model if isinstance(model, str) and 0 < len(model.strip()) <= 120 else "gemma3:4b",
        "model_scan_dir": location if isinstance(location, str) and len(location) <= 2048
                          and not any(ord(c) < 32 for c in location) else "",
    }


def save(prefs: dict[str, str], path: Path | None = None) -> None:
    dest = Path(path) if path is not None else path_settings()
    lang = prefs.get("language", "")
    model = prefs.get("ollama_model", "gemma3:4b").strip()
    location = prefs.get("model_scan_dir", "")
    if (lang not in ("", "pl", "en") or not isinstance(model, str)
            or not model or len(model) > 120 or not isinstance(location, str)
            or len(location) > 2048 or any(ord(c) < 32 for c in location)):
        raise ValueError("Invalid language, model or scan location")
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", dir=dest.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"language": lang, "ollama_model": model,
                       "model_scan_dir": location}, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dest)
        if os.name != "nt":
            os.chmod(dest, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
