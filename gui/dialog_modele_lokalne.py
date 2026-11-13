# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Wybór modeli Ollama oraz podgląd modeli lokalnych z dysku."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from gui.modele_worker import ZadanieModeli
from i18n import t
from uslugi.modele_lokalne import ModelNaDysku


class DialogModeleLokalne(QDialog):
    """Tylko modele z lokalnego API Ollamy są aktywne przy wyborze.

    Pliki w LM Studio, HF itd. to informacja o dysku, a nie pozwolenie
    na przekazanie arbitralnej ścieżki do /api/chat.
    """

    def __init__(self, parent=None, *, katalog_uzytkownika: str = ""):
        super().__init__(parent)
        self.setWindowTitle(t("models.title"))
        self.resize(760, 580)
        self.wybrany_model: str | None = None
        self.dostepne_modele: list[str] = []
        self.katalog_uzytkownika = katalog_uzytkownika
        self._zadanie: ZadanieModeli | None = None

        layout = QVBoxLayout(self)
        self.wskazowka = QLabel(t("models.hint"))
        self.wskazowka.setWordWrap(True)
        self.wskazowka.setObjectName("podpowiedz")
        layout.addWidget(self.wskazowka)

        # Taki sam układ wyszukiwania jak w AI Bobrze:
        # lokalizacje standardowe i folder wskazany przez użytkownika.
        self.standardowe = QCheckBox(t("models.standard_locations"))
        self.standardowe.setObjectName("modeleStandardowe")
        self.standardowe.setChecked(True)
        layout.addWidget(self.standardowe)
        custom = QHBoxLayout()
        self.katalog = QLineEdit(self.katalog_uzytkownika)
        self.katalog.setObjectName("katalogSkanowaniaModeli")
        self.katalog.setReadOnly(True)
        self.katalog.setPlaceholderText(t("models.custom_empty"))
        self.katalog.setToolTip(t("models.custom_hint"))
        custom.addWidget(self.katalog, 1)
        self.btn_katalog = QPushButton(t("models.browse_folder"))
        self.btn_katalog.setObjectName("przeszukajFolderModeli")
        self.btn_katalog.clicked.connect(self._wybierz_katalog)
        custom.addWidget(self.btn_katalog)
        self.btn_wyczysc_katalog = QPushButton(t("models.clear_folder"))
        self.btn_wyczysc_katalog.setObjectName("usunFolderModeli")
        self.btn_wyczysc_katalog.clicked.connect(self._wyczysc_katalog)
        custom.addWidget(self.btn_wyczysc_katalog)
        layout.addLayout(custom)

        self.karty = QTabWidget()
        layout.addWidget(self.karty, 1)

        self.strona_ollama = QWidget()
        ol = QVBoxLayout(self.strona_ollama)
        self.lista_ollama = QListWidget()
        self.lista_ollama.setObjectName("lokalneModeleOllama")
        self.lista_ollama.itemSelectionChanged.connect(self._zmieniono)
        self.lista_ollama.itemDoubleClicked.connect(self._zatwierdz)
        ol.addWidget(self.lista_ollama, 1)
        self.opis_ollama = QLabel(t("models.api_only"))
        self.opis_ollama.setWordWrap(True)
        self.opis_ollama.setObjectName("podpowiedz")
        ol.addWidget(self.opis_ollama)
        self.karty.addTab(self.strona_ollama, t("models.ollama_tab"))

        self.strona_dysk = QWidget()
        dl = QVBoxLayout(self.strona_dysk)
        self.lista_dysk = QListWidget()
        self.lista_dysk.setObjectName("modeleTylkoNaDysku")
        self.lista_dysk.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        dl.addWidget(self.lista_dysk, 1)
        info = QLabel(t("models.disk_hint"))
        info.setWordWrap(True)
        info.setObjectName("podpowiedz")
        dl.addWidget(info)
        self.karty.addTab(self.strona_dysk, t("models.disk_tab"))

        self.status = QLabel(t("models.searching"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.btn_ponow = QPushButton(t("models.refresh"))
        self.btn_ponow.setObjectName("szukajLokalnie")
        self.btn_ponow.clicked.connect(self.odswiez)
        buttons.addWidget(self.btn_ponow)
        buttons.addStretch()
        self.btn_uzyj = QPushButton(t("models.choose"))
        self.btn_uzyj.setEnabled(False)
        self.btn_uzyj.clicked.connect(self._zatwierdz)
        buttons.addWidget(self.btn_uzyj)
        # Dopiero po utworzeniu przycisków: currentChanged wyzwala się też
        # podczas dodawania pierwszej zakładki.
        self.karty.currentChanged.connect(self._zmieniono)
        self.btn_zamknij = QPushButton(t("models.close"))
        self.btn_zamknij.clicked.connect(self.reject)
        buttons.addWidget(self.btn_zamknij)
        layout.addLayout(buttons)
        self.odswiez()

    def _wybierz_katalog(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, t("models.browse_folder"), self.katalog_uzytkownika or str(Path.home())
        )
        if chosen:
            self.katalog_uzytkownika = chosen
            self.katalog.setText(chosen)
            self.odswiez()

    def _wyczysc_katalog(self) -> None:
        self.katalog_uzytkownika = ""
        self.katalog.clear()
        self.odswiez()

    def odswiez(self) -> None:
        if self._zadanie is not None:
            return
        self.wybrany_model = None
        self.lista_ollama.clear()
        self.lista_dysk.clear()
        self.btn_uzyj.setEnabled(False)
        self.btn_ponow.setEnabled(False)
        self.btn_katalog.setEnabled(False)
        self.btn_wyczysc_katalog.setEnabled(False)
        self.standardowe.setEnabled(False)
        self.status.setText(t("models.searching"))
        self._zadanie = ZadanieModeli(
            standardowe=self.standardowe.isChecked(),
            dodatkowy=self.katalog_uzytkownika,
        )
        self._zadanie.sygnaly.gotowe.connect(self._gotowe)
        QThreadPool.globalInstance().start(self._zadanie)

    def _gotowe(self, available: list[str], disk: list[ModelNaDysku],
                error: str) -> None:
        self._zadanie = None
        self.btn_ponow.setEnabled(True)
        self.btn_katalog.setEnabled(True)
        self.btn_wyczysc_katalog.setEnabled(True)
        self.standardowe.setEnabled(True)
        self.dostepne_modele = list(available)
        for name in available:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.lista_ollama.addItem(item)
        if not available:
            item = QListWidgetItem(t("models.no_ollama"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.lista_ollama.addItem(item)
        for item in disk:
            row = QListWidgetItem(f"{item.nazwa}  [{item.program}]")
            row.setToolTip(str(item.sciezka))
            self.lista_dysk.addItem(row)
        if not disk:
            item = QListWidgetItem(t("models.no_disk"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.lista_dysk.addItem(item)
        if error:
            self.status.setText(t("models.no_service", error=error))
        else:
            self.status.setText(t("models.found", count=len(available),
                                  disk=len(disk)))
        self._zmieniono()

    def _zmieniono(self) -> None:
        current = self.lista_ollama.currentItem()
        enabled = (self.karty.currentIndex() == 0 and self._zadanie is None
                   and current is not None
                   and isinstance(current.data(Qt.ItemDataRole.UserRole), str))
        self.btn_uzyj.setEnabled(enabled)

    def _zatwierdz(self, *_args) -> None:
        current = self.lista_ollama.currentItem()
        if self.karty.currentIndex() != 0 or current is None or self._zadanie is not None:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(name, str) or not name.strip():
            return
        self.wybrany_model = name
        self.accept()

    def reject(self) -> None:
        if self._zadanie is not None:
            self._zadanie.przerwij.set()
        super().reject()

    def closeEvent(self, event) -> None:
        if self._zadanie is not None:
            self._zadanie.przerwij.set()
        super().closeEvent(event)
