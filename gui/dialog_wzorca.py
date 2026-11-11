# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Przyjazny formularz edycji wzorca z podglądem JSON wyłącznie do odczytu.

Samo otwarcie i edycja dialogu niczego nie zapisują. Zapis wykonuje
MagazynWzorcow po wyraźnym potwierdzeniu przez użytkownika.
"""
from __future__ import annotations

import copy
import json

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from i18n import t
from uslugi.wzorce import POLA_WZORCA, zatwierdz_strukture

# W tej samej kolejności co pola prezentowane przez analizę Gemmy.
POLA_FORMULARZA = (
    ("dostawca", "ai.label.supplier"),
    ("numer_faktury", "ai.label.invoice"),
    ("kwota_do_zaplaty", "ai.label.amount"),
    ("waluta", "ai.label.currency"),
    ("data_wystawienia", "ai.label.issued"),
    ("termin_platnosci", "ai.label.due"),
    ("okres_od", "ai.label.from"),
    ("okres_do", "ai.label.to"),
    ("numer_konta_bankowego", "ai.label.account"),
    ("kategoria_sugerowana", "ai.label.category"),
)
FORMATY = ("", "DD.MM.RRRR", "RRRR-MM-DD", "MM/RRRR", "PLN", "NRB_OR_IBAN")


def _linie(text: str) -> list[str]:
    """Jedna etykieta lub instrukcja na linię."""
    return [item.strip() for item in text.splitlines() if item.strip()]


def _tekst_wieloliniowy(value: list[str], height: int = 74) -> QPlainTextEdit:
    editor = QPlainTextEdit()
    editor.setPlainText("\n".join(value))
    editor.setMaximumHeight(height)
    return editor


class DialogWzorca(QDialog):
    def __init__(self, parent, proposed: dict, *, aktualizacja: bool = False):
        super().__init__(parent)
        self.wejscie = zatwierdz_strukture(proposed)
        self.zatwierdzone: dict | None = None
        self.setWindowTitle(t(
            "patterns.dialog.update" if aktualizacja else "patterns.dialog.new"
        ))
        self.resize(860, 670)
        layout = QVBoxLayout(self)

        intro = QLabel(t("patterns.form.intro"))
        intro.setWordWrap(True)
        intro.setObjectName("podpowiedz")
        layout.addWidget(intro)

        self.karty = QTabWidget()
        self.karty.setObjectName("kartyWzorca")
        layout.addWidget(self.karty, 1)
        self._dane_podstawowe()
        self._reguly_pol()
        self._podglad_json()
        self.karty.currentChanged.connect(self._odswiez_podglad)

        self.przyciski = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.przyciski.button(
            QDialogButtonBox.StandardButton.Save
        ).setText(t("patterns.dialog.approve"))
        self.przyciski.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText(t("settings.cancel"))
        self.przyciski.accepted.connect(self._zatwierdz)
        self.przyciski.rejected.connect(self.reject)
        layout.addWidget(self.przyciski)

    def _dane_podstawowe(self) -> None:
        panel = QWidget()
        form = QFormLayout(panel)
        form.setSpacing(10)
        data = self.wejscie
        identification = data["identification"]

        self.nazwa = QLineEdit(data["name"])
        self.nazwa.setObjectName("nazwaWzorca")
        form.addRow(t("patterns.form.name"), self.nazwa)

        self.nip = QLineEdit(identification["seller_nip"] or "")
        self.nip.setPlaceholderText(t("patterns.form.nip_placeholder"))
        form.addRow(t("patterns.form.nip"), self.nip)

        self.aliasy = _tekst_wieloliniowy(identification["seller_aliases"])
        form.addRow(t("patterns.form.aliases"), self.aliasy)

        self.etykiety = _tekst_wieloliniowy(identification["layout_labels"], 105)
        form.addRow(t("patterns.form.layout"), self.etykiety)

        self.kategoria = QLineEdit(data["category"] or "")
        form.addRow(t("patterns.form.category"), self.kategoria)

        self.status = QComboBox()
        self.status.addItem(t("patterns.form.active"), "approved")
        self.status.addItem(t("patterns.form.inactive"), "inactive")
        self.status.setCurrentIndex(
            self.status.findData(data["status"])
        )
        form.addRow(t("patterns.form.status"), self.status)

        self.wskazowki = _tekst_wieloliniowy(data["agent_notes"], 135)
        form.addRow(t("patterns.form.notes"), self.wskazowki)
        self.karty.addTab(panel, t("patterns.form.general_tab"))

    def _reguly_pol(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        hint = QLabel(t("patterns.form.rules_hint"))
        hint.setWordWrap(True)
        hint.setObjectName("podpowiedz")
        layout.addWidget(hint)
        self.pola: dict[str, dict] = {}
        for name, label in POLA_FORMULARZA:
            config = self.wejscie["fields"].get(name, {})
            group = QGroupBox(t(label))
            group.setObjectName("regula_" + name)
            group.setCheckable(True)
            group.setChecked(name in self.wejscie["fields"])
            form = QFormLayout(group)

            source = _tekst_wieloliniowy(config.get("find_by", []))
            form.addRow(t("patterns.form.find_by"), source)

            source_format = QComboBox()
            target_format = QComboBox()
            for combo in (source_format, target_format):
                combo.addItem(t("patterns.form.no_format"), "")
                for format_name in FORMATY[1:]:
                    combo.addItem(format_name, format_name)
            source_format.setCurrentIndex(
                source_format.findData(config.get("source_format", ""))
            )
            target_format.setCurrentIndex(
                target_format.findData(config.get("target_format", ""))
            )
            form.addRow(t("patterns.form.source_format"), source_format)
            form.addRow(t("patterns.form.target_format"), target_format)

            note = QPlainTextEdit(config.get("note", ""))
            note.setMaximumHeight(85)
            form.addRow(t("patterns.form.field_note"), note)
            self.pola[name] = {
                "group": group, "find_by": source, "source_format": source_format,
                "target_format": target_format, "note": note,
            }
            layout.addWidget(group)
        layout.addStretch()
        scroll.setWidget(panel)
        self.karty.addTab(scroll, t("patterns.form.rules_tab"))

    def _podglad_json(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        info = QLabel(t("patterns.form.preview_hint"))
        info.setWordWrap(True)
        layout.addWidget(info)
        self.podglad = QPlainTextEdit()
        self.podglad.setObjectName("podgladJSON")
        self.podglad.setReadOnly(True)
        layout.addWidget(self.podglad)
        self.karty.addTab(panel, t("patterns.form.preview_tab"))

    def zbuduj_dane(self) -> dict:
        """Zbierz widoczne pola i sprawdź schemat, niczego jeszcze nie zapisuj."""
        doc = copy.deepcopy(self.wejscie)
        doc["name"] = self.nazwa.text().strip()
        doc["identification"] = {
            "seller_nip": self.nip.text().strip().replace(" ", "").replace("-", "") or None,
            "seller_aliases": _linie(self.aliasy.toPlainText()),
            "layout_labels": _linie(self.etykiety.toPlainText()),
        }
        doc["category"] = self.kategoria.text().strip() or None
        doc["status"] = self.status.currentData()
        doc["agent_notes"] = _linie(self.wskazowki.toPlainText())
        doc["fields"] = {}
        for name, ui in self.pola.items():
            if ui["group"].isChecked():
                doc["fields"][name] = {
                    "find_by": _linie(ui["find_by"].toPlainText()),
                    "source_format": ui["source_format"].currentData(),
                    "target_format": ui["target_format"].currentData(),
                    "note": ui["note"].toPlainText().strip(),
                }
        return zatwierdz_strukture(doc)

    def _odswiez_podglad(self, tab: int) -> None:
        if tab != 2:
            return
        try:
            data = self.zbuduj_dane()
            self.podglad.setPlainText(
                json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
            )
        except (ValueError, TypeError) as exc:
            self.podglad.setPlainText(t("patterns.form.error", error=exc))

    def _zatwierdz(self) -> None:
        try:
            self.zatwierdzone = self.zbuduj_dane()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, t("patterns.title"), str(exc))
            return  # dialog pozostaje otwarty, dane nie zostały zapisane
        self.accept()


def zaakceptuj_wzorzec(parent, proposed: dict, *, aktualizacja: bool = False) -> dict | None:
    """Użytkownik edytuje formularz; JSON jest zapisywany dopiero po odrębnej zgodzie."""
    dialog = DialogWzorca(parent, proposed, aktualizacja=aktualizacja)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.zatwierdzone
