# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Odkrywanie lokalnych modeli AI bez wysyłania danych poza komputer.

Podział odpowiada AI Bobrowi:
- Ollama /api/tags: nazwy, które można uruchomić przez obecny backend Świstaka.
- Magazyny na dysku: informacja o plikach, NIE lista działających modeli.
Inne GGUF wymagają osobnego importu do Ollamy, zanim staną się dostępne.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

_HOST = "http://127.0.0.1:11434"
_MODEL_LAYER = "application/vnd.ollama.image.model"
_MAX_REPLY = 2 * 1024 * 1024
_MAX_MANIFEST = 256 * 1024
_MAX_ITEMS = 150
_MAX_FILES = 12000
_MAX_DEPTH = 8
_IGNORED = {"node_modules", "__pycache__", "site-packages", ".git", "tmp",
            "partial", "incomplete", "venv", ".venv"}


class BladOllama(RuntimeError):
    """Lokalny serwer Ollama nie jest dostępny albo zwrócił błędne dane."""


@dataclass(frozen=True)
class ModelNaDysku:
    nazwa: str
    program: str
    sciezka: Path


def _nazwa_modelu(tekst: object) -> str | None:
    if not isinstance(tekst, str):
        return None
    name = tekst.strip()
    # Są to wyłącznie nazwy do wyświetlenia, nie polecenia powłoki.
    if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
        return None
    return name


def modele_ollama(*, timeout: float = 4) -> list[str]:
    """Lista modeli z localhost /api/tags. Nie skanuje sieci ani nie pobiera wag."""
    if not 0 < timeout <= 30:
        raise ValueError("Nieprawidłowy czas odczytu Ollamy")
    req = Request(_HOST + "/api/tags", headers={"Accept": "application/json"})
    try:
        # Wyłączenie proxy jest ważne: wywołanie ma zawsze pozostać lokalne.
        with build_opener(ProxyHandler({})).open(req, timeout=timeout) as response:
            payload = response.read(_MAX_REPLY + 1)
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise BladOllama("Ollama nie odpowiada pod 127.0.0.1:11434") from exc
    if len(payload) > _MAX_REPLY:
        raise BladOllama("Odpowiedź Ollamy jest zbyt duża")
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise BladOllama("Ollama zwróciła niepoprawny JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise BladOllama("Ollama zwróciła niepoprawną listę modeli")
    names: set[str] = set()
    for model in data["models"][:1000]:
        if not isinstance(model, dict):
            continue
        name = _nazwa_modelu(model.get("name") or model.get("model"))
        # Modele embeddingowe nie służą do generowania pól faktury.
        family = str((model.get("details") or {}).get("family") or "").lower() \
            if isinstance(model.get("details") or {}, dict) else ""
        if name and "embed" not in name.lower() and "embed" not in family:
            names.add(name)
    return sorted(names, key=str.casefold)


def znane_lokalizacje(*, home: Path | None = None,
                      env: Mapping[str, str] | None = None,
                      platform: str | None = None) -> list[tuple[str, Path]]:
    """Ograniczone lokalizacje z wzorca AI Bobra, Linux/macOS/Windows."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    platform = sys.platform if platform is None else platform
    windows = platform.startswith("win")
    cache = Path(env.get("XDG_CACHE_HOME") or home / ".cache")
    data = Path(env.get("XDG_DATA_HOME") or home / ".local" / "share")
    local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
    roots: list[tuple[str, Path]] = []

    def add(app: str, path: Path | str | None) -> None:
        if path:
            roots.append((app, Path(path).expanduser()))

    add("Ollama", env.get("OLLAMA_MODELS"))
    add("Ollama", home / ".ollama" / "models")
    if not windows and platform != "darwin":
        add("Ollama", "/usr/share/ollama/.ollama/models")
        add("Ollama", "/var/lib/ollama/.ollama/models")
        add("Ollama", "/var/lib/ollama")
    add("LM Studio", home / ".lmstudio" / "models")
    add("LM Studio", home / ".cache" / "lm-studio" / "models")
    add("Hugging Face", env.get("HF_HUB_CACHE") or
        (Path(env["HF_HOME"]) / "hub" if env.get("HF_HOME") else
         cache / "huggingface" / "hub"))
    add("llama.cpp", env.get("LLAMA_CACHE") or
        (local / "llama.cpp" if windows else cache / "llama.cpp"))
    add("GPT4All", local / "nomic.ai" / "GPT4All" if windows else
        data / "nomic.ai" / "GPT4All")
    uniq: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for app, path in roots:
        try:
            key = str(path.resolve())
            if key not in seen and path.is_dir():
                uniq.append((app, path))
                seen.add(key)
        except OSError:
            continue
    return uniq


def _pliki(root: Path, *, stop: threading.Event | None = None) -> Iterable[Path]:
    """Ogranicz koszt skanu; nie podążaj za dowiązaniami katalogów."""
    count = 0
    for directory, subdirs, files in os.walk(root, followlinks=False):
        if stop is not None and stop.is_set():
            return
        folder = Path(directory)
        depth = len(folder.relative_to(root).parts)
        if depth >= _MAX_DEPTH:
            subdirs[:] = []
        else:
            subdirs[:] = sorted(x for x in subdirs
                                if not x.startswith(".") and x.lower() not in _IGNORED)
        for filename in sorted(files):
            count += 1
            if count > _MAX_FILES:
                return
            yield folder / filename


def _magazyn_ollama(store: Path, stop: threading.Event | None = None) -> list[ModelNaDysku]:
    """Odczytaj same manifesty i istnienie blobu, bez otwierania wag."""
    manifests = store / "manifests"
    blobs = store / "blobs"
    if not manifests.is_dir() or not blobs.is_dir():
        return []
    found: list[ModelNaDysku] = []
    for manifest in _pliki(manifests, stop=stop):
        if len(found) >= _MAX_ITEMS:
            break
        try:
            relative = manifest.relative_to(manifests).parts
            if len(relative) < 3 or manifest.stat().st_size > _MAX_MANIFEST:
                continue
            data = json.loads(manifest.read_text(encoding="utf-8"))
            layers = data.get("layers") if isinstance(data, dict) else None
            if not isinstance(layers, list):
                continue
            layer = next((v for v in layers if isinstance(v, dict)
                          and v.get("mediaType") == _MODEL_LAYER), None)
            if not layer:
                continue
            digest = layer.get("digest")
            if not isinstance(digest, str) or not digest.startswith("sha256:"):
                continue
            sha = digest.removeprefix("sha256:")
            if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha.lower()):
                continue
            blob = blobs / ("sha256-" + sha)
            if not blob.is_file():
                continue
            registry, *tail = relative
            tag = tail.pop()
            if registry == "registry.ollama.ai" and tail and tail[0] == "library":
                tail.pop(0)
            if not tail:
                continue
            name = _nazwa_modelu(
                "/".join(([registry] if registry != "registry.ollama.ai" else []) + tail)
                + ":" + tag
            )
            if name and "embed" not in name.lower():
                found.append(ModelNaDysku(name, "Ollama", blob))
        except (OSError, ValueError, TypeError):
            continue
    return found


def lokalizacje_skanowania(
    *, standardowe: bool = True, dodatkowy: Path | str | None = None,
) -> list[tuple[str, Path]]:
    """Znane miejsca plus folder wskazany przez użytkownika, bez duplikatów.

    Magazyn Ollamy rozpoznajemy po manifests/ i blobs/; wybranie
    samego folderu magazynu nie wymaga uruchamiania API.
    """
    result = znane_lokalizacje() if standardowe else []
    if dodatkowy:
        root = Path(dodatkowy).expanduser()
        if not root.is_dir():
            raise ValueError("Wybrany katalog modeli nie istnieje")
        store = root if (root / "manifests").is_dir() and (root / "blobs").is_dir() else (
            root / "models" if (root / "models" / "manifests").is_dir()
            and (root / "models" / "blobs").is_dir() else None
        )
        if store is not None:
            result.append(("Ollama", store))
        else:
            result.append(("Wskazany katalog", root))
    unique: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for label, root in result:
        try:
            resolved = Path(root).resolve()
        except (OSError, ValueError):
            continue
        if resolved not in seen and resolved.is_dir():
            unique.append((label, Path(root)))
            seen.add(resolved)
    return unique


def modele_na_dysku(
    *, lokalizacje: Iterable[tuple[str, Path]] | None = None,
    stop: threading.Event | None = None,
) -> list[ModelNaDysku]:
    """Szybki skan znanych folderów. Nigdy nie ładuje ani nie uruchamia wag."""
    places = znane_lokalizacje() if lokalizacje is None else list(lokalizacje)
    found: list[ModelNaDysku] = []
    seen: set[tuple[str, str]] = set()
    for app, root in places:
        if stop is not None and stop.is_set():
            break
        root = Path(root)
        if app == "Ollama":
            items = _magazyn_ollama(root, stop)
        else:
            items = []
            for path in _pliki(root, stop=stop):
                if len(items) >= _MAX_ITEMS:
                    break
                if path.suffix.lower() != ".gguf" or "-partial" in path.name.lower():
                    continue
                try:
                    # Cztery bajty zamiast wczytywania gigabajtowych wag.
                    with path.open("rb") as source:
                        if source.read(4) != b"GGUF":
                            continue
                except OSError:
                    continue
                name = _nazwa_modelu(path.stem)
                if name:
                    items.append(ModelNaDysku(name, app, path))
        for item in items:
            # Dysk to informacja pomocnicza, nie dowód gotowości w Ollamie.
            key = (item.program, item.nazwa.casefold())
            if key not in seen:
                found.append(item)
                seen.add(key)
            if len(found) >= _MAX_ITEMS:
                break
        if len(found) >= _MAX_ITEMS:
            break
    return sorted(found, key=lambda item: (item.program, item.nazwa.casefold()))
