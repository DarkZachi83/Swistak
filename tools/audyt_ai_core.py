# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""AI Core 1.0 — bezpieczny, deterministyczny audyt kontraktów i paczek.

Bez uruchamiania Ollamy, bez otwierania prywatnych faktur i bez
przeglądania katalogów domowych. Zero operacji zapisu.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ai_core.gateway import ToolGateway
from ai_core.ollama import OllamaProvider
from tools.build_linux_beta import manifest
from tools.build_linux_binary import BINARY_DATA

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_RUNTIME = frozenset({
    "ai_core/__init__.py",
    "ai_core/contracts.py", "ai_core/errors.py", "ai_core/gateway.py",
    "ai_core/hybrid.py", "ai_core/hybrid_queue.py", "ai_core/ollama.py",
    "ai_core/orchestrator.py", "ai_core/provider.py", "ai_core/router.py",
    "docs/ai_core/contracts_v1.schema.json",
    "docs/ai_core/tools_v1.json",
})
MUST_NOT_SHIP_SUFFIXES = (".pdf", ".sqlite3", ".db", ".db3", ".key", ".pem")
MUST_NOT_SHIP_PARTS = {
    ".venv", ".git", "__pycache__", "kopie_migracji", "dokumenty",
    "archive", "backups", "prywatne",
}


def run_audit() -> dict[str, object]:
    """Zwróć raport lub zgłoś ValueError, gdy paczka jest niekompletna."""
    source = manifest()
    source_paths = set(source)
    missing = REQUIRED_RUNTIME - source_paths
    if missing:
        raise ValueError("Brak elementów AI Core w źródłowej paczce: "
                         + ", ".join(sorted(missing)))

    for name in source_paths:
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts
                or any(part in MUST_NOT_SHIP_PARTS for part in path.parts)
                or name.lower().endswith(MUST_NOT_SHIP_SUFFIXES)):
            raise ValueError("Niebezpieczny wpis manifestu źródłowego: " + name)
    binary_paths = {entry for entry, _destination in BINARY_DATA}
    required_binary = {
        "docs/ai_core/contracts_v1.schema.json",
        "docs/ai_core/tools_v1.json",
    }
    if not required_binary.issubset(binary_paths):
        raise ValueError("Brak schematów AI Core w paczce PyInstaller")

    root_schema = json.loads(
        (ROOT / "docs/ai_core/contracts_v1.schema.json").read_text("utf-8")
    )
    Draft202012Validator.check_schema(root_schema)
    catalog = json.loads(
        (ROOT / "docs/ai_core/tools_v1.json").read_text("utf-8")
    )
    if catalog.get("catalog_version") != "1.0" or catalog.get("read_only") is not True:
        raise ValueError("Nieobsługiwana wersja katalogu narzędzi")
    tools = catalog.get("tools")
    if not isinstance(tools, list) or len(tools) != 12:
        raise ValueError("Nieoczekiwana liczba narzędzi w kontrakcie v1")
    names: set[str] = set()
    for entry in tools:
        if entry.get("effect") != "read" or entry["name"] in names:
            raise ValueError("Nieuprawnione lub powtórzone narzędzie")
        names.add(entry["name"])
        Draft202012Validator.check_schema(entry["input_schema"])

    # Sam kontrakt lokalności nie może zaakceptować chmurowego endpointu
    # także wtedy, gdy jest podany jako parametr do adaptera.
    for url in ("https://127.0.0.1:11434", "http://example.com:11434",
                "http://127.0.0.1:11434/other", "http://user@localhost:11434"):
        try:
            OllamaProvider(base_url=url)
        except ValueError:
            continue
        raise ValueError("Ollama zaakceptowała nielokalny endpoint: " + url)
    OllamaProvider()  # bez otwierania połączenia sieciowego
    gateway = ToolGateway(ROOT / "nonexistent-audit-database.sqlite3")
    if len(gateway.catalog) != 12:
        raise ValueError("Gateway nie wczytał kompletnego katalogu")
    if not set(gateway.catalog).issubset(names):
        raise ValueError("Gateway używa nieznanego narzędzia")
    return {
        "contract_version": "1.0",
        "runtime_files": len(REQUIRED_RUNTIME),
        "source_files": len(source_paths),
        "read_only_tools": len(names),
        "binary_schemas": len(required_binary),
        "local_only": True,
        "private_documents_read": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audyt AI Core 1.0 i pakowania")
    parser.add_argument("--check", action="store_true",
                        help="Zgłoś błąd, jeśli niezgodne są kontrakty lub paczki")
    args = parser.parse_args()
    try:
        report = run_audit()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("AI CORE AUDIT: FAIL —", exc)
        return 1
    print("AI CORE AUDIT: OK")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
