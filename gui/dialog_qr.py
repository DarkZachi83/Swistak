# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bezpieczny, lokalny podgląd kodów QR z dokumentu PDF."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

from gui.qr_worker import ZadanieQR
from i18n import t
from uslugi.kody_qr import KodQR, PlatnoscQR
from uslugi.rachunki import grosze_na_kwote


class DialogQR(QDialog):
    """QR niczego nie zapisuje. Wybór danych płatniczych wymaga zgody."""
    def __init__(self, parent, pdf: str | Path):
        super().__init__(parent)
        self.setWindowTitle(t("qr.title"))
        self.resize(680, 460)
        self.wybrana_platnosc: PlatnoscQR | None = None
        self._zadanie: ZadanieQR | None = None
        layout = QVBoxLayout(self)
        self.informacja = QLabel(t("qr.running"))
        self.informacja.setWordWrap(True)
        layout.addWidget(self.informacja)
        self.pole = QPlainTextEdit()
        self.pole.setReadOnly(True)
        self.pole.setPlaceholderText(t("qr.placeholder"))
        layout.addWidget(self.pole, 1)
        self.przyciski = QDialogButtonBox()
        self.zastosuj = self.przyciski.addButton(
            t("qr.apply"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.zastosuj.setEnabled(False)
        self.zastosuj.clicked.connect(self._zastosuj)
        self.zamknij = self.przyciski.addButton(
            t("qr.close"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.zamknij.clicked.connect(self.reject)
        layout.addWidget(self.przyciski)
        self._start(Path(pdf))

    def _start(self, pdf: Path) -> None:
        self._zadanie = ZadanieQR(pdf)
        self._zadanie.sygnaly.gotowe.connect(self._gotowe)
        self._zadanie.sygnaly.blad.connect(self._blad)
        self._zadanie.sygnaly.anulowano.connect(self._anulowano)
        QThreadPool.globalInstance().start(self._zadanie)

    def _gotowe(self, wynik: tuple[KodQR, ...]) -> None:
        self._zadanie = None
        if not wynik:
            self.informacja.setText(t("qr.none"))
            return
        self.informacja.setText(t("qr.found", count=len(wynik)))
        znalezione = [x.platnosc for x in wynik if x.platnosc is not None]
        # Nie wybieraj arbitralnie jednego z wielu rachunków płatniczych.
        if len(znalezione) == 1:
            self.wybrana_platnosc = znalezione[0]
            self.zastosuj.setEnabled(True)
        for nr, kod in enumerate(wynik, 1):
            if kod.platnosc is None:
                tekst = t("qr.unknown") + "\n" + kod.tresc
            else:
                p = kod.platnosc
                tekst = "\n".join((
                    t("qr.payment"),
                    t("qr.recipient") + ": " + p.odbiorca,
                    t("qr.nip") + ": " + p.nip,
                    t("qr.account") + ": " + p.numer_konta,
                    t("qr.amount") + ": " + grosze_na_kwote(p.kwota_grosze) + " PLN",
                    t("qr.transfer_title") + ": " + p.tytul,
                ))
            self.pole.appendPlainText(
                t("qr.code", number=nr, page=kod.strona + 1) + "\n" + tekst + "\n"
            )

    def _blad(self, komunikat: str) -> None:
        self._zadanie = None
        self.informacja.setText(t("qr.error"))
        QMessageBox.warning(self, t("qr.title"), komunikat)

    def _anulowano(self) -> None:
        self._zadanie = None
        self.informacja.setText(t("qr.cancelled"))

    def _zastosuj(self) -> None:
        p = self.wybrana_platnosc
        if p is None:
            return
        odpowiedz = QMessageBox.question(
            self, t("qr.title"),
            t("qr.confirm", amount=grosze_na_kwote(p.kwota_grosze), account=p.numer_konta),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if odpowiedz == QMessageBox.StandardButton.Yes:
            self.accept()

    def reject(self) -> None:
        if self._zadanie is not None:
            self._zadanie.przerwij.set()
        super().reject()

    def closeEvent(self, event) -> None:
        if self._zadanie is not None:
            self._zadanie.przerwij.set()
        super().closeEvent(event)
