# SPDX-License-Identifier: GPL-3.0-only
"""Świstak — podgląd PDF, import, formularz i lokalna lista rachunków."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSplitter, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget, QComboBox,
)

from gui.podglad_pdf import PodgladPDF
from uslugi.geometria import Zaznaczenie
from uslugi.rachunki import DaneRachunku, RejestrRachunkow, grosze_na_kwote


class OknoGlowne(QMainWindow):
    def __init__(self, rejestr: RejestrRachunkow):
        super().__init__()
        self.rejestr = rejestr
        self.aktualny_dokument_id: int | None = None
        self.setWindowTitle("Świstak — rachunki (etap 1)")
        self.resize(1250, 820)
        self.setMinimumSize(870, 560)

        centrum = QWidget()
        self.setCentralWidget(centrum)
        pion = QVBoxLayout(centrum)
        pion.setContentsMargins(15, 14, 15, 14)
        pion.setSpacing(12)

        naglowek = QHBoxLayout()
        tytul = QLabel("Świstak")
        tytul.setObjectName("naglowek")
        naglowek.addWidget(tytul)
        opis = QLabel("Archiwum rachunków • etap 1")
        opis.setObjectName("podpowiedz")
        naglowek.addWidget(opis)
        naglowek.addStretch()
        pion.addLayout(naglowek)

        pasek = QFrame()
        pasek.setObjectName("pasek")
        przyciski = QHBoxLayout(pasek)
        przyciski.setContentsMargins(10, 8, 10, 8)
        przyciski.setSpacing(7)

        self.otworz_przycisk = QPushButton("Importuj PDF")
        self.otworz_przycisk.clicked.connect(self.wybierz_plik)
        przyciski.addWidget(self.otworz_przycisk)

        self.poprzednia = QPushButton("◀ Poprzednia")
        self.poprzednia.clicked.connect(lambda: self._zmien_strone(-1))
        przyciski.addWidget(self.poprzednia)

        self.strony = QLabel("Brak dokumentu")
        self.strony.setMinimumWidth(100)
        self.strony.setAlignment(Qt.AlignmentFlag.AlignCenter)
        przyciski.addWidget(self.strony)

        self.nastepna = QPushButton("Następna ▶")
        self.nastepna.clicked.connect(lambda: self._zmien_strone(1))
        przyciski.addWidget(self.nastepna)
        przyciski.addStretch()
        for etykieta, akcja in (
            ("−", lambda: self.podglad.powieksz(0.8)),
            ("+", lambda: self.podglad.powieksz(1.25)),
            ("Dopasuj", self.podglad_dopasuj),
        ):
            przycisk = QPushButton(etykieta)
            przycisk.clicked.connect(akcja)
            przyciski.addWidget(przycisk)
        pion.addWidget(pasek)

        dzielnik = QSplitter(Qt.Orientation.Horizontal)
        self.podglad = PodgladPDF()
        self.podglad.zaznaczono.connect(self._zaznaczenie)
        self.podglad.zmiana_strony.connect(self._aktualizuj_nawigacje)
        dzielnik.addWidget(self.podglad)

        self.karty = QTabWidget()
        self.karty.setMinimumWidth(315)
        self.karty.addTab(self._zbuduj_formularz(), "Rachunek")
        self.karty.addTab(self._zbuduj_liste(), "Dokumenty")
        dzielnik.addWidget(self.karty)
        dzielnik.setStretchFactor(0, 3)
        dzielnik.setStretchFactor(1, 2)
        dzielnik.setSizes([800, 410])
        pion.addWidget(dzielnik, 1)

        self.opis_zaznaczenia = QLabel("Zaznacz fragment PDF lewym przyciskiem myszy.")
        self.opis_zaznaczenia.setObjectName("podpowiedz")
        pion.addWidget(self.opis_zaznaczenia)
        self.statusBar().showMessage("Importowane oryginały PDF pozostają poza repozytorium Git")
        self._aktualizuj_nawigacje(0, 0)
        self._odswiez_liste()
        self._wyczysc_formularz()

    def _zbuduj_formularz(self) -> QWidget:
        przewijanie = QScrollArea()
        przewijanie.setWidgetResizable(True)
        przewijanie.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(10, 14, 10, 12)
        uklad.setSpacing(10)
        self.nazwa_dokumentu = QLabel("Najpierw zaimportuj dokument PDF.")
        self.nazwa_dokumentu.setWordWrap(True)
        uklad.addWidget(self.nazwa_dokumentu)
        forma = QFormLayout()
        forma.setSpacing(8)

        self.ed_dostawca = QLineEdit()
        self.ed_numer = QLineEdit()
        self.ed_kwota = QLineEdit()
        self.ed_kwota.setPlaceholderText("np. 245,80")
        self.ed_wystawiono = QLineEdit()
        self.ed_termin = QLineEdit()
        self.ed_od = QLineEdit()
        self.ed_do = QLineEdit()
        for pole in (self.ed_wystawiono, self.ed_termin, self.ed_od, self.ed_do):
            pole.setPlaceholderText("RRRR-MM-DD (opcjonalnie)")

        self.wybor_kategoria = QComboBox()
        wybor_i_dodaj = QWidget()
        kategoria_uklad = QHBoxLayout(wybor_i_dodaj)
        kategoria_uklad.setContentsMargins(0, 0, 0, 0)
        kategoria_uklad.addWidget(self.wybor_kategoria, 1)
        dodaj = QPushButton("+")
        dodaj.setToolTip("Dodaj nową kategorię")
        dodaj.clicked.connect(self._dodaj_kategorie)
        kategoria_uklad.addWidget(dodaj)

        self.wybor_status = QComboBox()
        self.wybor_status.addItem("Do zapłaty", "do_zaplaty")
        self.wybor_status.addItem("Opłacony", "oplacony")
        self.ed_uwagi = QTextEdit()
        self.ed_uwagi.setPlaceholderText("Opcjonalna notatka")
        self.ed_uwagi.setMaximumHeight(86)

        for etykieta, element in (
            ("Dostawca *", self.ed_dostawca),
            ("Nr rachunku", self.ed_numer),
            ("Kwota [zł] *", self.ed_kwota),
            ("Kategoria *", wybor_i_dodaj),
            ("Wystawiono", self.ed_wystawiono),
            ("Termin płatności", self.ed_termin),
            ("Okres od", self.ed_od),
            ("Okres do", self.ed_do),
            ("Status", self.wybor_status),
            ("Uwagi", self.ed_uwagi),
        ):
            forma.addRow(etykieta, element)
        uklad.addLayout(forma)
        self.zapisz_przycisk = QPushButton("Zapisz rachunek")
        self.zapisz_przycisk.clicked.connect(self._zapisz_rachunek)
        uklad.addWidget(self.zapisz_przycisk)
        komunikat = QLabel("Etap 1: pola wpisujesz ręcznie. Odczyt ze wskazanego obszaru PDF pojawi się w etapie 2.")
        komunikat.setWordWrap(True)
        komunikat.setObjectName("podpowiedz")
        uklad.addWidget(komunikat)
        uklad.addStretch()
        przewijanie.setWidget(panel)
        return przewijanie

    def _zbuduj_liste(self) -> QWidget:
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(8, 10, 8, 10)
        opis = QLabel("Wybierz zaimportowany dokument, aby go otworzyć lub uzupełnić.")
        opis.setWordWrap(True)
        uklad.addWidget(opis)
        self.lista_dokumentow = QListWidget()
        self.lista_dokumentow.itemClicked.connect(self._wybierz_z_listy)
        uklad.addWidget(self.lista_dokumentow)
        przycisk = QPushButton("Odśwież listę")
        przycisk.clicked.connect(self._odswiez_liste)
        uklad.addWidget(przycisk)
        return panel

    def _odswiez_kategorie(self, wybrana: int | None = None) -> None:
        self.wybor_kategoria.clear()
        for wiersz in self.rejestr.kategorie():
            self.wybor_kategoria.addItem(wiersz["nazwa"], int(wiersz["id"]))
        if wybrana is not None:
            numer = self.wybor_kategoria.findData(wybrana)
            if numer >= 0:
                self.wybor_kategoria.setCurrentIndex(numer)

    def _dodaj_kategorie(self) -> None:
        nazwa, zaakceptowano = QInputDialog.getText(self, "Nowa kategoria", "Nazwa kategorii:")
        if not zaakceptowano:
            return
        try:
            identyfikator = self.rejestr.dodaj_kategorie(nazwa)
            self._odswiez_kategorie(identyfikator)
        except (ValueError, sqlite3.Error) as blad:
            QMessageBox.warning(self, "Kategoria", str(blad))

    def _odswiez_liste(self) -> None:
        self.lista_dokumentow.clear()
        for wiersz in self.rejestr.dokumenty():
            opis = f"{wiersz['nazwa_zrodlowa']}"
            if wiersz["kwota_grosze"] is not None:
                opis = (f"✓ {wiersz['dostawca']} — "
                        f"{grosze_na_kwote(wiersz['kwota_grosze'])} zł\n"
                        f"   {wiersz['nazwa_zrodlowa']}")
            else:
                opis = "○ Do uzupełnienia\n   " + opis
            element = QListWidgetItem(opis)
            element.setData(Qt.ItemDataRole.UserRole, int(wiersz["id"]))
            self.lista_dokumentow.addItem(element)

    def _wyczysc_formularz(self) -> None:
        self.nazwa_dokumentu.setText("Najpierw zaimportuj dokument PDF.")
        for pole in (self.ed_dostawca, self.ed_numer, self.ed_kwota, self.ed_wystawiono,
                     self.ed_termin, self.ed_od, self.ed_do):
            pole.clear()
        self.ed_uwagi.clear()
        self.wybor_status.setCurrentIndex(0)
        self._odswiez_kategorie()
        self.zapisz_przycisk.setEnabled(False)

    def _wyswietl_dokument(self, dokument_id: int) -> None:
        sciezka = self.rejestr.sciezka_pdf(dokument_id)
        # Przy błędzie (np. uszkodzony plik archiwalny) nie pozwalaj zapisywać
        # pól pod niewłaściwym dokumentem.
        self.aktualny_dokument_id = None
        self.zapisz_przycisk.setEnabled(False)
        self.podglad.otworz(sciezka)
        dokument = self.rejestr.dokument(dokument_id)
        self.aktualny_dokument_id = dokument_id
        self.nazwa_dokumentu.setText("Oryginał: " + dokument["nazwa_zrodlowa"])
        zapis = self.rejestr.rachunek(dokument_id)
        self._wyczysc_formularz()
        self.nazwa_dokumentu.setText("Oryginał: " + dokument["nazwa_zrodlowa"])
        if zapis is not None:
            self.ed_dostawca.setText(zapis["dostawca"])
            self.ed_numer.setText(zapis["numer"])
            self.ed_kwota.setText(grosze_na_kwote(zapis["kwota_grosze"]))
            self.ed_wystawiono.setText(zapis["data_wystawienia"] or "")
            self.ed_termin.setText(zapis["termin_platnosci"] or "")
            self.ed_od.setText(zapis["okres_od"] or "")
            self.ed_do.setText(zapis["okres_do"] or "")
            self.ed_uwagi.setPlainText(zapis["uwagi"])
            self._odswiez_kategorie(zapis["kategoria_id"])
            idx = self.wybor_status.findData(zapis["status"])
            if idx >= 0:
                self.wybor_status.setCurrentIndex(idx)
        self.zapisz_przycisk.setEnabled(True)
        self.karty.setCurrentIndex(0)
        self.statusBar().showMessage("Otworzono z prywatnego archiwum: " + dokument["nazwa_zrodlowa"])

    def _wybierz_z_listy(self, element: QListWidgetItem) -> None:
        try:
            self._wyswietl_dokument(int(element.data(Qt.ItemDataRole.UserRole)))
        except (ValueError, OSError, sqlite3.Error) as blad:
            QMessageBox.warning(self, "Nie można otworzyć dokumentu", str(blad))

    def podglad_dopasuj(self) -> None:
        self.podglad.dopasuj()

    def wybierz_plik(self) -> None:
        sciezka, _ = QFileDialog.getOpenFileName(
            self, "Importuj rachunek", "", "Pliki PDF (*.pdf)"
        )
        if sciezka:
            self.otworz_pdf(sciezka)

    def otworz_pdf(self, sciezka: str | Path) -> None:
        try:
            # Zweryfikuj PDF w Qt przed dodaniem go do archiwum i bazy.
            self.aktualny_dokument_id = None
            self.zapisz_przycisk.setEnabled(False)
            self.podglad.otworz(sciezka)
            dokument_id, czy_nowy = self.rejestr.importuj_pdf(sciezka)
            self._wyswietl_dokument(dokument_id)
            self._odswiez_liste()
            if not czy_nowy:
                self.statusBar().showMessage("Ten PDF jest już w archiwum — otwarto istniejący dokument.")
        except (OSError, ValueError, sqlite3.Error) as blad:
            QMessageBox.warning(self, "Nie można importować PDF", str(blad))

    def _zapisz_rachunek(self) -> None:
        if self.aktualny_dokument_id is None:
            return
        try:
            dane = DaneRachunku(
                dokument_id=self.aktualny_dokument_id,
                dostawca=self.ed_dostawca.text(),
                numer=self.ed_numer.text(),
                kwota=self.ed_kwota.text(),
                kategoria_id=self.wybor_kategoria.currentData(),
                data_wystawienia=self.ed_wystawiono.text(),
                termin_platnosci=self.ed_termin.text(),
                okres_od=self.ed_od.text(),
                okres_do=self.ed_do.text(),
                status=self.wybor_status.currentData(),
                uwagi=self.ed_uwagi.toPlainText(),
            )
            self.rejestr.zapisz_rachunek(dane)
            self._odswiez_liste()
            self.statusBar().showMessage("Rachunek zapisany w lokalnej bazie SQLite.")
        except (ValueError, OSError, sqlite3.Error) as blad:
            QMessageBox.warning(self, "Nie można zapisać rachunku", str(blad))

    def _zmien_strone(self, krok: int) -> None:
        try:
            self.podglad.pokaz_strone(self.podglad.strona + krok)
        except ValueError as blad:
            QMessageBox.warning(self, "Błąd renderowania", str(blad))

    def _aktualizuj_nawigacje(self, numer: int, razem: int) -> None:
        self.strony.setText(f"{numer + 1} / {razem}" if razem else "Brak dokumentu")
        self.poprzednia.setEnabled(razem > 0 and numer > 0)
        self.nastepna.setEnabled(razem > 0 and numer + 1 < razem)

    def _zaznaczenie(self, pole: Zaznaczenie | None) -> None:
        if pole is None:
            self.opis_zaznaczenia.setText("Zaznacz fragment PDF lewym przyciskiem myszy.")
            return
        self.opis_zaznaczenia.setText(
            f"Strona {pole.strona + 1} | obszar względny: "
            f"lewo={pole.lewo:.4f}, góra={pole.gora:.4f}, "
            f"prawo={pole.prawo:.4f}, dół={pole.dol:.4f} "
            "— odczyt wartości pojawi się w etapie 2."
        )
