# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Zakładka odczytu tekstu z PDF lub skanu."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, Signal, Slot
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget

from gui.odczyt_worker import ZadanieOdczytu
from gui.uklad import Siatka
from i18n import t
from uslugi.geometria import Zaznaczenie
from uslugi.odczyt_pdf import WynikOdczytu


class ZakladkaOdczytu(QWidget):
    """Odczyt PDF i OCR, wybór zakresu oraz podgląd uzyskanego tekstu."""

    odczyt_zadany = Signal(bool)  # tylko zaznaczony obszar
    analiza_zadana = Signal()
    qr_zadany = Signal()
    tekst_zmieniony = Signal()
    tekst_odczytany = Signal()
    stan_pracy_zmieniony = Signal()
    status_zmieniony = Signal(str, dict)

    def __init__(self):
        """Podgląd surowego tekstu, zanim trafi do Ollamy."""
        super().__init__()
        self._zadanie_odczytu: ZadanieOdczytu | None = None
        uklad = QVBoxLayout(self)
        uklad.setContentsMargins(10, 12, 10, 12)
        uklad.setSpacing(10)
        instrukcja = QLabel()
        self.hint_odczytu = instrukcja
        instrukcja.setWordWrap(True)
        instrukcja.setObjectName("podpowiedz")
        uklad.addWidget(instrukcja)
        przyciski = Siatka(3)
        self.btn_odczytaj = QPushButton()
        self.btn_odczytaj.clicked.connect(self._zlec_caly_pdf)
        przyciski.dodaj(self.btn_odczytaj)
        self.btn_odczytaj_obszar = QPushButton()
        self.btn_odczytaj_obszar.clicked.connect(self._zlec_obszar)
        przyciski.dodaj(self.btn_odczytaj_obszar)
        self.btn_odczytaj_qr = QPushButton()
        self.btn_odczytaj_qr.setObjectName("odczytajQR")
        self.btn_odczytaj_qr.clicked.connect(self.qr_zadany)
        przyciski.dodaj(self.btn_odczytaj_qr)
        uklad.addWidget(przyciski)
        self.btn_anuluj = QPushButton()
        self.btn_anuluj.clicked.connect(self._anuluj_odczyt)
        uklad.addWidget(self.btn_anuluj)
        self.info_odczytu = QLabel()
        self.info_odczytu.setWordWrap(True)
        uklad.addWidget(self.info_odczytu)
        self.pole_odczytu = QTextEdit()
        self.pole_odczytu.setReadOnly(True)
        uklad.addWidget(self.pole_odczytu, 1)
        kopiuj = QPushButton()
        self.btn_kopiuj = kopiuj
        kopiuj.clicked.connect(self._kopiuj_tekst)
        self.pole_odczytu.textChanged.connect(self.tekst_zmieniony)
        uklad.addWidget(kopiuj)
        self.btn_analizuj_z_odczytu = QPushButton()
        self.btn_analizuj_z_odczytu.clicked.connect(self.analiza_zadana)
        uklad.addWidget(self.btn_analizuj_z_odczytu)
        self.komunikat("read.start")

    @property
    def tekst(self) -> str:
        return self.pole_odczytu.toPlainText()

    @property
    def pracuje(self) -> bool:
        return self._zadanie_odczytu is not None

    def komunikat(self, klucz: str, **wartosci) -> None:
        self._komunikat = (klucz, wartosci)
        self.info_odczytu.setText(t(klucz, **wartosci))

    def przetlumacz(self) -> None:
        self.hint_odczytu.setText(t("read.hint"))
        self.btn_odczytaj.setText(t("button.read_all"))
        self.btn_odczytaj_obszar.setText(t("button.read_selection"))
        self.btn_odczytaj_qr.setText(t("qr.read"))
        self.btn_anuluj.setText(t("button.cancel"))
        self.btn_kopiuj.setText(t("button.copy"))
        self.pole_odczytu.setPlaceholderText(t("read.placeholder"))
        self.btn_analizuj_z_odczytu.setText(t("button.analyze_text"))
        klucz, wartosci = self._komunikat
        self.info_odczytu.setText(t(klucz, **wartosci))

    def ustaw_dostepnosc(self, *, dokument: bool, obszar: bool, analiza_trwa: bool) -> None:
        gotowy = dokument and not self.pracuje and not analiza_trwa
        self.btn_odczytaj.setEnabled(gotowy)
        self.btn_odczytaj_obszar.setEnabled(gotowy and obszar)
        self.btn_odczytaj_qr.setEnabled(gotowy)
        self.btn_anuluj.setEnabled(self.pracuje)
        self.btn_analizuj_z_odczytu.setEnabled(gotowy and bool(self.tekst.strip()))

    def resetuj_dokument(self) -> None:
        self.pole_odczytu.clear()
        self.komunikat("doc.opened")

    @Slot()
    def _zlec_caly_pdf(self) -> None:
        self.odczyt_zadany.emit(False)

    @Slot()
    def _zlec_obszar(self) -> None:
        self.odczyt_zadany.emit(True)

    @Slot()
    def _kopiuj_tekst(self) -> None:
        QApplication.clipboard().setText(self.tekst)

    def uruchom(self, sciezka: Path, obszar: Zaznaczenie | None) -> None:
        zadanie = ZadanieOdczytu(sciezka, obszar)
        self._zadanie_odczytu = zadanie
        self.pole_odczytu.clear()
        self.komunikat("read.running")
        self.stan_pracy_zmieniony.emit()
        zadanie.sygnaly.gotowe.connect(self._odczyt_gotowy)
        zadanie.sygnaly.blad.connect(self._odczyt_blad)
        zadanie.sygnaly.anulowano.connect(self._odczyt_anulowano)
        QThreadPool.globalInstance().start(zadanie)

    @Slot(object)
    def _odczyt_gotowy(self, wynik: WynikOdczytu) -> None:
        self._zadanie_odczytu = None
        self.pole_odczytu.setPlainText(wynik.tekst_dla_llm)
        self.tekst_odczytany.emit()
        self.stan_pracy_zmieniony.emit()
        if wynik.czy_pusty:
            self.komunikat("read.missing")
        else:
            statystyka = ", ".join(
                t("read.page_method", page=p.strona + 1, method=t("read.method_" + p.metoda))
                for p in wynik.strony
            )
            self.komunikat("read.done", count=len(wynik.strony), details=statystyka)
        self.status_zmieniony.emit("msg.read_status", {})

    @Slot(str)
    def _odczyt_blad(self, komunikat: str) -> None:
        self._zadanie_odczytu = None
        self.stan_pracy_zmieniony.emit()
        self.komunikat("read.error")
        QMessageBox.warning(self.window(), t("msg.pdf"), komunikat)

    @Slot()
    def _odczyt_anulowano(self) -> None:
        self._zadanie_odczytu = None
        self.stan_pracy_zmieniony.emit()
        self.komunikat("read.cancelled")

    def _anuluj_odczyt(self) -> None:
        if self._zadanie_odczytu is not None:
            self._zadanie_odczytu.przerwij.set()
            self.komunikat("msg.read_cancelling")

    def zamknij(self) -> None:
        if self._zadanie_odczytu is not None:
            self._zadanie_odczytu.przerwij.set()
