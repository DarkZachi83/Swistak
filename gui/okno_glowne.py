# SPDX-License-Identifier: GPL-3.0-only
"""Główne okno prototypu Świstaka (bez zapisu danych)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from gui.podglad_pdf import PodgladPDF
from uslugi.geometria import Zaznaczenie


class OknoGlowne(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Świstak — prototyp PDF (etap 0)")
        self.resize(1180, 800)
        self.setMinimumSize(800, 550)

        centrum = QWidget()
        self.setCentralWidget(centrum)
        pion = QVBoxLayout(centrum)
        pion.setContentsMargins(15, 14, 15, 14)
        pion.setSpacing(12)

        naglowek = QHBoxLayout()
        tytul = QLabel("Świstak")
        tytul.setObjectName("naglowek")
        naglowek.addWidget(tytul)
        opis = QLabel("Podgląd PDF • etap 0")
        opis.setObjectName("podpowiedz")
        naglowek.addWidget(opis)
        naglowek.addStretch()
        pion.addLayout(naglowek)

        pasek = QFrame()
        pasek.setObjectName("pasek")
        przyciski = QHBoxLayout(pasek)
        przyciski.setContentsMargins(10, 8, 10, 8)
        przyciski.setSpacing(7)

        self.otworz_przycisk = QPushButton("Otwórz PDF")
        self.otworz_przycisk.clicked.connect(self.wybierz_plik)
        przyciski.addWidget(self.otworz_przycisk)

        self.poprzednia = QPushButton("◀ Poprzednia")
        self.poprzednia.clicked.connect(lambda: self._zmien_strone(-1))
        przyciski.addWidget(self.poprzednia)

        self.strony = QLabel("Brak dokumentu")
        self.strony.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.strony.setMinimumWidth(100)
        przyciski.addWidget(self.strony)

        self.nastepna = QPushButton("Następna ▶")
        self.nastepna.clicked.connect(lambda: self._zmien_strone(1))
        przyciski.addWidget(self.nastepna)

        przyciski.addStretch()
        for etykieta, akcja in (("−", lambda: self.podglad.powieksz(0.8)),
                                ("+", lambda: self.podglad.powieksz(1.25)),
                                ("Dopasuj", self.podglad_dopasuj)):
            przycisk = QPushButton(etykieta)
            przycisk.clicked.connect(akcja)
            przyciski.addWidget(przycisk)
        pion.addWidget(pasek)

        self.podglad = PodgladPDF()
        self.podglad.zaznaczono.connect(self._zaznaczenie)
        self.podglad.zmiana_strony.connect(self._aktualizuj_nawigacje)
        pion.addWidget(self.podglad, 1)

        self.opis_zaznaczenia = QLabel("Zaznacz fragment PDF lewym przyciskiem myszy.")
        self.opis_zaznaczenia.setObjectName("podpowiedz")
        pion.addWidget(self.opis_zaznaczenia)
        self.statusBar().showMessage("Prototyp: dane nie są jeszcze zapisywane")
        self._aktualizuj_nawigacje(0, 0)

    def podglad_dopasuj(self) -> None:
        self.podglad.dopasuj()

    def wybierz_plik(self) -> None:
        sciezka, _ = QFileDialog.getOpenFileName(self, "Wybierz rachunek PDF", "", "Pliki PDF (*.pdf)")
        if sciezka:
            self.otworz_pdf(sciezka)

    def otworz_pdf(self, sciezka: str | Path) -> None:
        try:
            self.podglad.otworz(sciezka)
        except (OSError, ValueError) as blad:
            QMessageBox.warning(self, "Nie można otworzyć PDF", str(blad))
            self._aktualizuj_nawigacje(0, self.podglad.liczba_stron)
            return
        self.statusBar().showMessage(f"Otworzono: {Path(sciezka).name}")

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
            "— odczyt i zapis pojawią się w dalszych etapach."
        )
