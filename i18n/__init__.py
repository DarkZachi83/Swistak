# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bieżące tłumaczenia UI bez restartu; niezależna implementacja dla Qt.

Projekt rozwiązania oparty na sprawdzonym wzorcu AI Bobra: klucze JSON,
język systemowy jako opcja pusta, fallback brakującego klucza i
przeliczanie widoku przy zmianie języka. Nie importuje kodu AI Bobra.
"""
from __future__ import annotations

import json
import locale
import logging
import os
from pathlib import Path

LANGUAGES = ("pl", "en")
DEFAULT_LANGUAGE = "pl"
DIR = Path(__file__).resolve().parent
_cached: dict[str, dict[str, str]] = {}
_current = DEFAULT_LANGUAGE
_log = logging.getLogger(__name__)

def system_language(env: dict | None = None) -> str:
    env = os.environ if env is None else env
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = str(env.get(key, "")).strip().lower()
        # C/POSIX nie są językiem interfejsu; sprawdzamy kolejne zmienne.
        if value and value.split(".")[0] not in ("c", "posix"):
            break
    else:
        try:
            value = str(locale.getlocale()[0] or "").lower()
        except (TypeError, ValueError):
            value = ""
    return "pl" if value.startswith(("pl", "polish")) else "en"

def set_language(code: str | None) -> str:
    global _current
    _current = code if code in LANGUAGES else system_language() if not code else DEFAULT_LANGUAGE
    return _current

def current_language() -> str:
    return _current

def t(key: str, **fields) -> str:
    lang = _current
    def read(code: str) -> str | None:
        if code not in _cached:
            _cached[code] = json.loads((DIR / f"{code}.json").read_text(encoding="utf-8"))
        return _cached[code].get(key)
    value = read(lang) or read(DEFAULT_LANGUAGE) or key
    try:
        return value.format(**fields) if fields else value
    except (KeyError, ValueError, IndexError) as error:
        _log.warning("Translation %s: %s", key, error)
        return value
