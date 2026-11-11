# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Łącz reguły po korekcie człowieka, bez dopisywania kwot lub kont faktur."""
from __future__ import annotations

import copy

from uslugi.wzorce import zatwierdz_strukture


def zaproponuj_aktualizacje(aktualny: dict, odczytany: dict) -> dict:
    old = zatwierdz_strukture(aktualny)
    incoming = zatwierdz_strukture(odczytany)
    result = copy.deepcopy(old)
    prev = result["identification"]
    new = incoming["identification"]
    if prev["seller_nip"] and new["seller_nip"] and (
        prev["seller_nip"] != new["seller_nip"]
    ):
        raise ValueError("Inny NIP sprzedawcy — utwórz oddzielny wzorzec")
    if prev["seller_nip"] is None:
        prev["seller_nip"] = new["seller_nip"]
    for label in ("seller_aliases", "layout_labels"):
        prev[label] = list(dict.fromkeys([*prev[label], *new[label]]))
    if incoming["category"]:
        result["category"] = incoming["category"]
    for field, config in incoming["fields"].items():
        if field not in result["fields"]:
            result["fields"][field] = config
            continue
        old_config = result["fields"][field]
        old_config["find_by"] = list(dict.fromkeys([
            *old_config["find_by"], *config["find_by"],
        ]))
        for key in ("source_format", "target_format", "note"):
            if config[key]:
                old_config[key] = config[key]
    result["agent_notes"] = list(dict.fromkeys([
        *result["agent_notes"], *incoming["agent_notes"],
    ]))
    result["status"] = "approved"
    return zatwierdz_strukture(result)
