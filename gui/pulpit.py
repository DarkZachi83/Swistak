# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Pulpit rachunków oparty na danych SQLite i ostatnim raporcie Agenta."""
from __future__ import annotations

from collections import Counter
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ai_core.hybrid import MonitorReport, today_warsaw
from i18n import t
from uslugi.finanse import Finanse
from uslugi.historia import HistoriaRozliczen
from uslugi.rachunki import RejestrRachunkow, grosze_na_kwote


class Pulpit(QScrollArea):
    pokaz_faktury = Signal()
    pokaz_plan = Signal(str)
    pokaz_historie = Signal(str)
    pokaz_agenta = Signal()

    def __init__(self, rejestr: RejestrRachunkow):
        super().__init__()
        self.rejestr = rejestr
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        tresc = QWidget()
        self.setWidget(tresc)
        uklad = QVBoxLayout(tresc)
        uklad.setContentsMargins(6, 2, 8, 8)
        uklad.setSpacing(14)
        self.naglowek = QLabel()
        self.naglowek.setObjectName("pulpitTytul")
        uklad.addWidget(self.naglowek)

        self.tytuly = {}
        self.wartosci = {}
        self.opisy = {}
        self.napisy = []

        platnosci = self._sekcja(uklad, "dashboard.payments")
        platnosci.addWidget(self._przycisk("nav.invoices", self.pokaz_faktury.emit))
        self._karty(uklad, ("unpaid", "overdue", "due_soon"))

        rozliczenie = self._sekcja(uklad, "dashboard.month")
        miesiac_etykieta = QLabel()
        self.napisy.append((miesiac_etykieta, "dashboard.month_picker"))
        self.miesiac = QComboBox()
        self.miesiac.setObjectName("pulpitMiesiac")
        miesiac_etykieta.setBuddy(self.miesiac)
        rozliczenie.addWidget(miesiac_etykieta)
        rozliczenie.addWidget(self.miesiac)
        rozliczenie.addWidget(self._przycisk(
            "plan.tab.history", lambda: self.pokaz_historie.emit(self.miesiac.currentText())
        ))
        self._karty(uklad, ("billed", "paid_service", "payments_in_month"))

        dokumenty = self._sekcja(uklad, "dashboard.expected")
        dokumenty.addWidget(self._przycisk(
            "plan.tab.plan", lambda: self.pokaz_plan.emit(self.miesiac.currentText())
        ))
        self._karty(uklad, ("waiting", "missing", "uncertain"), opis=False)
        self.brak_oczekiwan = QLabel()
        self.brak_oczekiwan.setWordWrap(True)
        self.brak_oczekiwan.setObjectName("podpowiedz")
        self.napisy.append((self.brak_oczekiwan, "dashboard.no_expectations"))
        uklad.addWidget(self.brak_oczekiwan)

        agent = self._sekcja(uklad, "nav.agent")
        self.btn_panel_agenta = self._przycisk("agent.open_short", self.pokaz_agenta.emit)
        self.btn_panel_agenta.setObjectName("otworzPanelAgenta")
        agent.addWidget(self.btn_panel_agenta)
        self.stan_agenta = QLabel()
        self.stan_agenta.setWordWrap(True)
        self.stan_agenta.setObjectName("stanAgenta")
        uklad.addWidget(self.stan_agenta)
        self.raport_agenta = QLabel()
        self.raport_agenta.setWordWrap(True)
        self.raport_agenta.setTextFormat(Qt.TextFormat.PlainText)
        self.raport_agenta.setObjectName("podpowiedz")
        uklad.addWidget(self.raport_agenta)
        uklad.addStretch()

        self.miesiac.currentIndexChanged.connect(self.odswiez)

    def _sekcja(self, uklad, klucz: str) -> QHBoxLayout:
        wiersz = QHBoxLayout()
        etykieta = QLabel()
        etykieta.setObjectName("pulpitSekcja")
        self.napisy.append((etykieta, klucz))
        wiersz.addWidget(etykieta)
        wiersz.addStretch()
        uklad.addLayout(wiersz)
        return wiersz

    def _przycisk(self, klucz: str, akcja) -> QPushButton:
        przycisk = QPushButton()
        przycisk.clicked.connect(akcja)
        self.napisy.append((przycisk, klucz))
        return przycisk

    def _karty(self, uklad, klucze: tuple[str, ...], *, opis: bool = True) -> None:
        siatka = QGridLayout()
        siatka.setHorizontalSpacing(10)
        for kolumna, klucz in enumerate(klucze):
            karta = QFrame()
            karta.setObjectName("pulpitKarta")
            pion = QVBoxLayout(karta)
            pion.setContentsMargins(14, 12, 14, 12)
            pion.setSpacing(5)
            tytul = QLabel()
            tytul.setWordWrap(True)
            self.tytuly[klucz] = tytul
            pion.addWidget(tytul)
            pion.addStretch()
            wartosc = QLabel()
            wartosc.setObjectName("pulpitWartosc")
            self.wartosci[klucz] = wartosc
            pion.addWidget(wartosc)
            if opis:
                licznik = QLabel()
                licznik.setObjectName("podpowiedz")
                self.opisy[klucz] = licznik
                pion.addWidget(licznik)
            siatka.addWidget(karta, 0, kolumna)
            siatka.setColumnStretch(kolumna, 1)
        uklad.addLayout(siatka)

    def przetlumacz(self) -> None:
        self.naglowek.setText(t("nav.dashboard"))
        for widget, klucz in self.napisy:
            widget.setText(t(klucz))
        self.miesiac.setAccessibleName(t("dashboard.month_picker"))
        for klucz, etykieta in self.tytuly.items():
            etykieta.setText(t("dashboard." + klucz))

    def odswiez(self) -> None:
        historia = HistoriaRozliczen(self.rejestr.db)
        dzis = today_warsaw()
        biezacy = dzis[:7]
        wybrany = self.miesiac.currentText() or biezacy
        miesiace = historia.miesiace()
        lista = sorted(set(miesiace) | {biezacy, wybrany}, reverse=True)
        if lista != [self.miesiac.itemText(i) for i in range(self.miesiac.count())]:
            self.miesiac.blockSignals(True)
            self.miesiac.clear()
            self.miesiac.addItems(lista)
            self.miesiac.setCurrentText(wybrany)
            self.miesiac.blockSignals(False)

        sumy = {
            **Finanse(self.rejestr.db).podsumowanie_terminow(date.fromisoformat(dzis)),
            **historia.sumy_miesiaca(wybrany),
        }
        for klucz, opis in self.opisy.items():
            kwota = grosze_na_kwote(sumy[klucz + "_grosze"])
            self.wartosci[klucz].setText(f"{kwota} {t('invoices.currency')}")
            opis.setText(t("dashboard.invoice_count", count=sumy[klucz + "_count"]))

        stany = Counter(wiersz["state"] for wiersz in historia.oczekiwania(wybrany, dzisiaj=dzis))
        self.brak_oczekiwan.setVisible(not stany)
        for klucz in ("waiting", "missing", "uncertain"):
            self.wartosci[klucz].setText(str(stany[klucz]))

    def aktualizuj_agenta(self, stan: str, raport: MonitorReport | None) -> None:
        self.stan_agenta.setText(t(stan))
        if raport is None:
            self.raport_agenta.setText(t("agent.no_results"))
        else:
            self.raport_agenta.setText(t(
                "dashboard.agent_report",
                scope=t("agent.scope." + raport.mode),
                date=raport.reference_date,
                findings=len(raport.findings),
                proposals=len(raport.proposals),
            ))
