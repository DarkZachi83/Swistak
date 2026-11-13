# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Walidacja normatywnych kopert JSON Schema v1 bez zależności od modelu."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import InvalidResponse

_SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "ai_core" / "contracts_v1.schema.json"


@lru_cache(maxsize=8)
def _validator(kind: str) -> Draft202012Validator:
    root = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    if kind not in root["$defs"]:
        raise ValueError("Nieznany rodzaj koperty AI Core")
    # Lokalne definicje pozwalają rozwiązać odwołania #/$defs bez sieci.
    node = {"$schema": root["$schema"], "$defs": root["$defs"], **root["$defs"][kind]}
    return Draft202012Validator(node, format_checker=FormatChecker())


def validate(kind: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InvalidResponse("Odpowiedź AI nie jest obiektem JSON")
    error = next(iter(_validator(kind).iter_errors(payload)), None)
    if error is not None:
        # Nie dołączamy wartości z dokumentów ani treści promptu do komunikatu.
        loc = ".".join(str(part) for part in error.path)
        raise InvalidResponse(f"Niepoprawny kontrakt {kind}, pole: {loc or 'root'}")
    return payload


def sanitize_result(payload: dict[str, Any], task: dict[str, Any], model: str) -> dict[str, Any]:
    """W Etapie 1 brak Tool Gateway: model nie może sam potwierdzać dowodów."""
    validate("AnalysisResult", payload)
    if payload["task_id"] != task["task_id"] or payload["data_revision"] != task["data_revision"]:
        raise InvalidResponse("Odpowiedź dotyczy innego zadania lub wersji danych")
    if payload["model_id"] != model:
        raise InvalidResponse("Odpowiedź pochodzi od innego modelu")
    # Model nie może przyznać sobie statusu 'verified'. Referencje do
    # dowodów bez wykonania narzędzi nie mają podstawy zaufania.
    for finding in payload["findings"]:
        finding["verification"] = "unverified"
        finding["evidence"] = []
    for action in payload["proposed_actions"]:
        if action["expected_data_revision"] != task["data_revision"]:
            raise InvalidResponse("Propozycja odnosi się do nieaktualnej wersji danych")
        if action["requires_confirmation"] is not True:
            raise InvalidResponse("Operacja nie posiada wymaganej zgody")
    validate("AnalysisResult", payload)
    return payload


def analysis_schema() -> dict[str, Any]:
    root = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    return {"$schema": root["$schema"], "$defs": root["$defs"], **root["$defs"]["AnalysisResult"]}
