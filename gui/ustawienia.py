# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Osadzony formularz konfiguracji modeli z jawnym zapisem zmian."""
from __future__ import annotations

from PySide6.QtCore import QThreadPool, Slot
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from gui.dialog_modele_lokalne import DialogModeleLokalne
from gui.modele_worker import ZadanieListyOllama
from i18n import t
from ustawienia import SPECIALIST_ROLES


class Ustawienia(QScrollArea):
    def __init__(self, katalog, zapisz):
        super().__init__()
        self.setObjectName("ustawieniaSwistaka")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.zapisz = zapisz
        self._stan = {}
        self._zadanie = None
        self._status = ("settings.models_loading", {})
        tresc = QWidget()
        self.setWidget(tresc)
        layout = QVBoxLayout(tresc)
        layout.setContentsMargins(6, 2, 8, 8)
        layout.setSpacing(12)
        self._napisy = []
        tytul = self._etykieta("settings.title")
        tytul.setObjectName("pulpitTytul")
        layout.addWidget(tytul)
        layout.addWidget(self._etykieta("settings.help"))
        layout.addWidget(self._etykieta("settings.model"))

        self.model = QComboBox()
        self.model.setObjectName("ustawieniaListaModeli")
        self.model.setEditable(True)
        self.model.setMinimumHeight(32)
        self.model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model.setMinimumContentsLength(22)
        layout.addWidget(self.model)
        row = QHBoxLayout()
        self.szukaj = QPushButton()
        self.szukaj.setObjectName("ustawieniaSzukajLokalnie")
        self.szukaj.clicked.connect(self._wybierz_model)
        row.addWidget(self.szukaj)
        row.addStretch()
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setObjectName("ustawieniaStatusModeli")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        layout.addWidget(self._etykieta("settings.model_scan_dir"))
        self.katalog_modeli = QLineEdit()
        self.katalog_modeli.setObjectName("ustawieniaKatalogModeli")
        self.katalog_modeli.setReadOnly(True)
        layout.addWidget(self.katalog_modeli)
        note = self._etykieta("settings.model_hint")
        note.setObjectName("ustawieniaOpisModeli")
        layout.addWidget(note)

        self.specjalisci = QGroupBox()
        self.specjalisci.setObjectName("ustawieniaModeleSpecjalistyczne")
        roles = QFormLayout(self.specjalisci)
        self.wybor_roli = {}
        for rola in SPECIALIST_ROLES:
            combo = QComboBox()
            combo.setObjectName("specialistModel_" + rola)
            combo.addItem("", "")
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(22)
            roles.addRow(self._etykieta("settings.specialists." + rola), combo)
            self.wybor_roli[rola] = combo
        layout.addWidget(self.specjalisci)
        layout.addWidget(self._etykieta("settings.data_dir"))
        folder = QLineEdit(str(katalog))
        folder.setReadOnly(True)
        layout.addWidget(folder)
        self.btn_wzorce = QPushButton()
        layout.addWidget(self.btn_wzorce, 0)
        layout.addStretch()

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._zastosuj)
        self.buttons.rejected.connect(self._przywroc)
        layout.addWidget(self.buttons)
        self.przetlumacz()

    def _etykieta(self, klucz):
        label = QLabel()
        label.setWordWrap(True)
        self._napisy.append((label, klucz))
        return label

    def przetlumacz(self):
        for etykieta, klucz in self._napisy:
            etykieta.setText(t(klucz))
        self.szukaj.setText(t("settings.find_models"))
        self.szukaj.setToolTip(t("models.search_hint"))
        self.katalog_modeli.setPlaceholderText(t("models.custom_empty"))
        self.katalog_modeli.setToolTip(t("models.custom_hint"))
        self.specjalisci.setTitle(t("settings.specialists.title"))
        for selector in self.wybor_roli.values():
            selector.setItemText(0, t("settings.specialists.default"))
        self.btn_wzorce.setText(t("patterns.manage"))
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("settings.apply"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("settings.cancel"))
        klucz, pola = self._status
        self.status.setText(t(klucz, **pola))

    def wczytaj(self, prefs, model):
        self._stan = {"ollama_model": model, "model_scan_dir": prefs.get("model_scan_dir", "")}
        self._stan.update({"model_" + r: prefs.get("model_" + r, "") for r in SPECIALIST_ROLES})
        self._przywroc()

    def _przywroc(self):
        if self.model.findText(self._stan["ollama_model"]) < 0:
            self.model.addItem(self._stan["ollama_model"])
        self.model.setCurrentText(self._stan["ollama_model"])
        self.katalog_modeli.setText(self._stan["model_scan_dir"])
        for rola, selector in self.wybor_roli.items():
            wybrany = self._stan["model_" + rola]
            if selector.findData(wybrany) < 0:
                selector.addItem(wybrany, wybrany)
            selector.setCurrentIndex(selector.findData(wybrany))

    def _ustaw_status(self, klucz, **pola):
        self._status = (klucz, pola)
        self.status.setText(t(klucz, **pola))

    def odswiez_modele(self):
        if self._zadanie is not None:
            return
        self._ustaw_status("settings.models_loading")
        self._zadanie = ZadanieListyOllama()
        self._zadanie.sygnaly.gotowe.connect(self._modele_gotowe)
        QThreadPool.globalInstance().start(self._zadanie)

    def anuluj_odswiezanie(self):
        if self._zadanie is not None:
            self._zadanie.przerwij.set()
            self._zadanie = None

    def _dodaj_modele(self, names):
        selected = self.model.currentText()
        unique = {}
        existing = [self.model.itemText(i) for i in range(self.model.count())]
        for name in [selected, *existing, *names]:
            if isinstance(name, str) and 0 < len(name.strip()) <= 120:
                unique.setdefault(name.strip().casefold(), name.strip())
        self.model.clear()
        self.model.addItems(list(unique.values()))
        self.model.setCurrentText(selected)
        for selector in self.wybor_roli.values():
            for name in names:
                if isinstance(name, str) and 0 < len(name.strip()) <= 120:
                    if selector.findData(name.strip()) < 0:
                        selector.addItem(name.strip(), name.strip())

    @Slot(object, str)
    def _modele_gotowe(self, names, error):
        self._zadanie = None
        self._dodaj_modele(names)
        if error:
            self._ustaw_status("settings.models_unavailable")
        elif names:
            self._ustaw_status("settings.models_found", count=len(names))
        else:
            self._ustaw_status("settings.models_empty")

    def _wybierz_model(self):
        picker = DialogModeleLokalne(self, katalog_uzytkownika=self.katalog_modeli.text())
        result = picker.exec()
        self.katalog_modeli.setText(picker.katalog_uzytkownika)
        self._dodaj_modele(picker.dostepne_modele)
        name = picker.wybrany_model
        if result == QDialog.DialogCode.Accepted and name:
            self._dodaj_modele([name])
            self.model.setCurrentText(name)
            self._ustaw_status("settings.models_found", count=self.model.count())
        picker.deleteLater()

    def _zastosuj(self):
        name = self.model.currentText().strip()
        if not name or len(name) > 120:
            QMessageBox.warning(self, t("settings.title"), t("settings.invalid"))
            return
        zmiany = {"ollama_model": name, "model_scan_dir": self.katalog_modeli.text()}
        zmiany.update({"model_" + r: c.currentData() or "" for r, c in self.wybor_roli.items()})
        if self.zapisz(zmiany):
            self.wczytaj(zmiany, name)
            self._ustaw_status("settings.saved")
