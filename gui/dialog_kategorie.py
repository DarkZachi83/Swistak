# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Kategorie: wybór istniejącej, świadome dodanie i bezpieczne scalenie.

Żadna operacja modyfikująca SQLite nie wykonuje się bez interakcji użytkownika.
Scalanie aktualizuje referencje w transakcji i pozostawia oryginalne PDF-y.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from i18n import t
from uslugi.kategorie import (
    PODSTAWOWE_KATEGORIE, klucz_kategorii, podobne_kategorie,
)
from uslugi.rachunki import RejestrRachunkow
from uslugi.wzorce import MagazynWzorcow


class DialogScalKategorie(QDialog):
    """Przenieś przypisania wyłącznie kategorii dodanej przez użytkownika."""
    def __init__(self, rejestr: RejestrRachunkow,
                 wzorce: MagazynWzorcow, parent=None):
        super().__init__(parent)
        self.rejestr = rejestr
        self.wzorce = wzorce
        self.wybrany_cel: int | None = None
        self.setWindowTitle(t("categories.merge.title"))
        self.setMinimumWidth(570)
        self.dane = rejestr.kategorie_z_uzyciem()
        layout = QVBoxLayout(self)
        opis = QLabel(t("categories.merge.hint"))
        opis.setWordWrap(True)
        layout.addWidget(opis)
        layout.addWidget(QLabel(t("categories.merge.source")))
        self.zrodlo = QComboBox()
        self.zrodlo.addItem(t("form.choose_category"), None)
        for row in self.dane:
            if row["nazwa"] not in PODSTAWOWE_KATEGORIE:
                self.zrodlo.addItem(
                    t("categories.entry", name=row["nazwa"],
                      count=int(row["liczba_faktur"])), int(row["id"])
                )
        layout.addWidget(self.zrodlo)
        layout.addWidget(QLabel(t("categories.merge.target")))
        self.cel = QComboBox()
        self.cel.addItem(t("form.choose_category"), None)
        for row in self.dane:
            self.cel.addItem(row["nazwa"], int(row["id"]))
        layout.addWidget(self.cel)
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_scal = QPushButton(t("categories.merge.action"))
        self.btn_scal.setEnabled(False)
        self.btn_scal.clicked.connect(self._wykonaj)
        buttons.addWidget(self.btn_scal)
        cancel = QPushButton(t("categories.cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.zrodlo.currentIndexChanged.connect(self._podpowiedz)
        self.cel.currentIndexChanged.connect(self._podpowiedz)
        self._podpowiedz()

    def _podpowiedz(self, *_args) -> None:
        source, target = self.zrodlo.currentData(), self.cel.currentData()
        valid = (isinstance(source, int) and isinstance(target, int)
                 and source != target)
        self.btn_scal.setEnabled(valid)
        if valid:
            row = next((v for v in self.dane if v["id"] == source), None)
            count = int(row["liczba_faktur"]) if row else 0
            self.info.setText(t("categories.merge.preview", count=count))
        else:
            self.info.setText(t("categories.merge.select_both"))

    def _wykonaj(self) -> None:
        source = self.zrodlo.currentData()
        target = self.cel.currentData()
        if not isinstance(source, int) or not isinstance(target, int) or source == target:
            return
        names = {int(row["id"]): row["nazwa"] for row in self.dane}
        old_name, new_name = names.get(source), names.get(target)
        if not old_name or not new_name:
            return
        # Wzorzec odwołuje się do tekstowej nazwy kategorii, a nie ID.
        # Nie wolno pozostawić wzorca z niedostępną nazwą po scaleniu.
        try:
            linked = [
                v["name"] for v in self.wzorce.lista()
                if v.get("category") and
                klucz_kategorii(v["category"]) == klucz_kategorii(old_name)
            ]
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self, t("categories.merge.title"),
                t("categories.merge.pattern_error", error=str(exc))
            )
            return
        if linked:
            QMessageBox.warning(
                self, t("categories.merge.title"),
                t("categories.merge.pattern_block", names=", ".join(linked[:5]))
            )
            return
        count = next(
            (int(v["liczba_faktur"]) for v in self.dane if v["id"] == source), 0
        )
        confirm = QMessageBox.question(
            self, t("categories.merge.title"),
            t("categories.merge.confirm", source=old_name, target=new_name,
              count=count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self.rejestr.scal_kategorie(source, target)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, t("categories.merge.title"), str(exc))
            return
        self.wybrany_cel = target
        self.accept()


class DialogKategorie(QDialog):
    """Najpierw pokaż istniejące kategorie; tworzenie jest odrębną decyzją."""
    def __init__(self, rejestr: RejestrRachunkow,
                 wzorce: MagazynWzorcow, parent=None):
        super().__init__(parent)
        self.rejestr = rejestr
        self.wzorce = wzorce
        self.wybrana_id: int | None = None
        self.setWindowTitle(t("categories.title"))
        self.setMinimumSize(570, 520)
        layout = QVBoxLayout(self)
        opis = QLabel(t("categories.hint"))
        opis.setWordWrap(True)
        layout.addWidget(opis)
        self.lista = QListWidget()
        self.lista.setObjectName("listaIstniejacychKategorii")
        self.lista.itemDoubleClicked.connect(self._wybierz)
        layout.addWidget(self.lista, 1)
        self.btn_wybierz = QPushButton(t("categories.choose"))
        self.btn_wybierz.setEnabled(False)
        self.btn_wybierz.clicked.connect(self._wybierz)
        self.lista.itemSelectionChanged.connect(
            lambda: self.btn_wybierz.setEnabled(self.lista.currentItem() is not None)
        )
        layout.addWidget(self.btn_wybierz)

        layout.addWidget(QLabel(t("categories.new_label")))
        self.nowa = QLineEdit()
        self.nowa.setObjectName("nazwaNowejKategorii")
        self.nowa.setPlaceholderText(t("categories.new_placeholder"))
        self.nowa.textChanged.connect(self._podpowiedz)
        layout.addWidget(self.nowa)
        self.podobne = QLabel(t("categories.new_hint"))
        self.podobne.setWordWrap(True)
        layout.addWidget(self.podobne)
        buttons = QHBoxLayout()
        self.btn_dodaj = QPushButton(t("categories.create"))
        self.btn_dodaj.clicked.connect(self._dodaj)
        self.btn_dodaj.setEnabled(False)
        buttons.addWidget(self.btn_dodaj)
        self.btn_scal = QPushButton(t("categories.merge.open"))
        self.btn_scal.clicked.connect(self._scal)
        buttons.addWidget(self.btn_scal)
        buttons.addStretch()
        cancel = QPushButton(t("categories.cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self._odswiez()

    def _odswiez(self) -> None:
        self.dane = self.rejestr.kategorie_z_uzyciem()
        self.lista.clear()
        for row in self.dane:
            item = QListWidgetItem(
                t("categories.entry", name=row["nazwa"],
                  count=int(row["liczba_faktur"]))
            )
            item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
            self.lista.addItem(item)
        self.btn_scal.setEnabled(
            any(row["nazwa"] not in PODSTAWOWE_KATEGORIE for row in self.dane)
        )
        self._podpowiedz()

    def _podpowiedz(self, *_args) -> None:
        tekst = self.nowa.text().strip()
        self.btn_dodaj.setEnabled(bool(tekst))
        sugestie = podobne_kategorie(tekst, (row["nazwa"] for row in self.dane))
        if sugestie:
            self.podobne.setText(t(
                "categories.similar", names=", ".join(sugestie)
            ))
        else:
            self.podobne.setText(t("categories.new_hint"))

    def _wybierz(self, *_args) -> None:
        item = self.lista.currentItem()
        if item is None:
            return
        self.wybrana_id = int(item.data(Qt.ItemDataRole.UserRole))
        self.accept()

    def _dodaj(self) -> None:
        name = " ".join(self.nowa.text().split())
        if not name:
            return
        existing = next(
            (r for r in self.dane
             if klucz_kategorii(r["nazwa"]) == klucz_kategorii(name)),
            None,
        )
        if existing:
            QMessageBox.information(
                self, t("categories.title"),
                t("categories.already", name=existing["nazwa"])
            )
            for index in range(self.lista.count()):
                if self.lista.item(index).data(Qt.ItemDataRole.UserRole) == existing["id"]:
                    self.lista.setCurrentRow(index)
                    break
            return
        podobne = podobne_kategorie(name, (r["nazwa"] for r in self.dane))
        if podobne:
            confirm = QMessageBox.question(
                self, t("categories.title"),
                t("categories.similar_confirm",
                  name=name, existing=", ".join(podobne)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        try:
            created = self.rejestr.dodaj_kategorie(
                name, zezwol_na_podobna=bool(podobne)
            )
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, t("categories.title"), str(exc))
            return
        self.wybrana_id = created
        self.accept()

    def _scal(self) -> None:
        dialog = DialogScalKategorie(self.rejestr, self.wzorce, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.wybrana_id = dialog.wybrany_cel
            self.accept()
