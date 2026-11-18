# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Potwierdzenia nadpisania i zmiany kwoty opłaconej faktury."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from i18n import t
from uslugi.rachunki import DaneRachunku, RejestrRachunkow, grosze_na_kwote, kwota_na_grosze


def zapisz_z_potwierdzeniem(
    parent: QWidget, rejestr: RejestrRachunkow, dane: DaneRachunku,
) -> int | None:
    """Zwróć identyfikator zapisu lub None po odmowie potwierdzenia."""
    istniejaca = rejestr.znajdz_duplikat(dane)
    nadpisz_id = None
    wersja = None
    potwierdz_korekte = False
    if istniejaca is not None:
        nowa_kwota = kwota_na_grosze(dane.kwota)
        stara_kwota = int(istniejaca["kwota_grosze"])
        potwierdzenie = t(
            "invoice.duplicate_confirm",
            supplier=istniejaca["dostawca"],
            number=istniejaca["numer"] or t("invoice.missing_number"),
            filename=istniejaca["nazwa_zrodlowa"],
        )
        if (istniejaca["status"] == "oplacony" and dane.data_oplacenia
                and dane.data_oplacenia != istniejaca["data_oplacenia"]):
            potwierdzenie += "\n\n" + t(
                "invoice.payment_date_change",
                old=istniejaca["data_oplacenia"] or "—", new=dane.data_oplacenia,
            )
        odpowiedz = QMessageBox.question(
            parent, t("invoice.duplicate_title"), potwierdzenie,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if odpowiedz != QMessageBox.StandardButton.Yes:
            return None
        if istniejaca["status"] == "oplacony" and nowa_kwota != stara_kwota:
            potwierdz_korekte = QMessageBox.question(
                parent, t("invoice.paid_amount_title"),
                t("invoice.paid_amount_confirm",
                  old=grosze_na_kwote(stara_kwota), new=grosze_na_kwote(nowa_kwota)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes
            if not potwierdz_korekte:
                return None
        nadpisz_id = int(istniejaca["id"])
        wersja = int(istniejaca["wersja_rekordu"])
    return rejestr.zapisz_rachunek(
        dane, nadpisz_id=nadpisz_id, expected_version=wersja,
        potwierdz_korekte_oplaconej=potwierdz_korekte,
    )
