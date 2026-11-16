# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Filtry, porównanie i wykresy wydatków."""
from __future__ import annotations

from calendar import monthrange
from datetime import date

from PySide6.QtCore import QDate, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ai_core.hybrid import today_warsaw
from gui.uklad import Siatka
from i18n import category_name, current_language, t
from uslugi.rachunki import RejestrRachunkow, grosze_na_kwote
from uslugi.statystyki import BEZ_KATEGORII, StatystykiRachunkow, Suma, ZakresDat, Zestawienie


class Statystyki(QScrollArea):
    def __init__(self, rejestr: RejestrRachunkow):
        super().__init__()
        self.rejestr = rejestr
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        widok = QWidget()
        self.setWidget(widok)
        uklad = QVBoxLayout(widok)
        uklad.setContentsMargins(6, 2, 8, 8)
        uklad.setSpacing(12)
        self.tytul = QLabel()
        self.tytul.setObjectName("pulpitTytul")
        uklad.addWidget(self.tytul)

        self.od = self._pole_daty("statystykiOd")
        self.do = self._pole_daty("statystykiDo")
        self.podstawa = QComboBox()
        self.grupowanie = QComboBox()
        self.status = QComboBox()
        self.status_uslugi = None
        self.kategoria = QComboBox()
        self.dostawca = QComboBox()
        self.btn_miesiac = QPushButton()
        self.btn_rok = QPushButton()
        skroty = QHBoxLayout()
        skroty.addWidget(self.btn_miesiac)
        skroty.addWidget(self.btn_rok)
        skroty.addStretch()
        uklad.addLayout(skroty)

        filtry = Siatka(3, szerokosc=210)
        self.etykiety = []
        for pola in (
            (("from", self.od), ("to", self.do)),
            (("basis", self.podstawa), ("grouping", self.grupowanie)),
            (("category", self.kategoria), ("supplier", self.dostawca), ("status", self.status)),
        ):
            grupa = QWidget()
            formularz = QFormLayout(grupa)
            formularz.setContentsMargins(0, 0, 0, 0)
            formularz.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            for klucz, pole in pola:
                etykieta = QLabel()
                etykieta.setBuddy(pole)
                self.etykiety.append((klucz, etykieta))
                formularz.addRow(etykieta, pole)
                if isinstance(pole, QComboBox):
                    pole.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                    pole.setMinimumContentsLength(14)
            filtry.dodaj(grupa)
        uklad.addWidget(filtry)

        self.opis_podstawy = QLabel()
        self.opis_podstawy.setObjectName("podpowiedz")
        self.opis_podstawy.setWordWrap(True)
        uklad.addWidget(self.opis_podstawy)

        podsumowanie = Siatka(4, szerokosc=170)
        self.karty = {}
        for klucz in ("total", "paid", "unpaid", "comparison"):
            panel = QFrame()
            panel.setObjectName("pulpitKarta")
            pion = QVBoxLayout(panel)
            tytul, wartosc, opis = QLabel(), QLabel(), QLabel()
            wartosc.setObjectName("pulpitWartosc")
            opis.setObjectName("podpowiedz")
            for etykieta in (tytul, wartosc, opis):
                etykieta.setWordWrap(True)
                pion.addWidget(etykieta)
            self.karty[klucz] = (tytul, wartosc, opis)
            podsumowanie.dodaj(panel)
        uklad.addWidget(podsumowanie)

        self.porownanie = QLabel()
        self.porownanie.setWordWrap(True)
        self.porownanie.setObjectName("podpowiedz")
        uklad.addWidget(self.porownanie)
        self.komunikat = QLabel()
        self.komunikat.setWordWrap(True)
        uklad.addWidget(self.komunikat)

        self.zakladki = QTabWidget()
        self.tabele = {}
        for klucz in ("periods", "categories", "suppliers"):
            tabela = QTableWidget()
            tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tabela.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            tabela.setAlternatingRowColors(True)
            tabela.verticalHeader().setVisible(False)
            tabela.verticalHeader().setDefaultSectionSize(32)
            self.tabele[klucz] = tabela
            self.zakladki.addTab(tabela, "")
        self.zakladki.setMinimumHeight(245)
        uklad.addWidget(self.zakladki, 1)

        self._ustaw_zakres("miesiac")
        self.btn_miesiac.clicked.connect(lambda: self._ustaw_zakres("miesiac"))
        self.btn_rok.clicked.connect(lambda: self._ustaw_zakres("rok"))
        for pole in (self.od, self.do):
            pole.dateChanged.connect(self._oblicz)
        self.podstawa.currentIndexChanged.connect(self._zmien_podstawe)
        for pole in (self.grupowanie, self.status, self.kategoria, self.dostawca):
            pole.currentIndexChanged.connect(self._oblicz)
        self.nazwy_kategorii = {}
        self.przetlumacz()

    @staticmethod
    def _pole_daty(nazwa: str) -> QDateEdit:
        pole = QDateEdit()
        pole.setObjectName(nazwa)
        pole.setDateRange(QDate(1, 1, 1), QDate(9999, 12, 31))
        pole.setDisplayFormat("yyyy-MM-dd")
        pole.setCalendarPopup(True)
        pole.setKeyboardTracking(False)
        return pole

    def _ustaw_zakres(self, grupowanie: str) -> None:
        dzis = date.fromisoformat(today_warsaw())
        if grupowanie == "rok":
            poczatek, koniec = QDate(dzis.year, 1, 1), QDate(dzis.year, 12, 31)
        else:
            poczatek = QDate(dzis.year, dzis.month, 1)
            koniec = QDate(dzis.year, dzis.month, monthrange(dzis.year, dzis.month)[1])
        with QSignalBlocker(self.od), QSignalBlocker(self.do), QSignalBlocker(self.grupowanie):
            self.od.setDate(poczatek)
            self.do.setDate(koniec)
            indeks = self.grupowanie.findData(grupowanie)
            if indeks < 0:
                return
            self.grupowanie.setCurrentIndex(indeks)
        self._oblicz()

    @staticmethod
    def _opcje(pole: QComboBox, opcje) -> None:
        wybor = pole.currentData()
        with QSignalBlocker(pole):
            pole.clear()
            for opis, wartosc in opcje:
                pole.addItem(opis, wartosc)
            pole.setCurrentIndex(max(0, pole.findData(wybor)))

    def przetlumacz(self) -> None:
        self.tytul.setText(t("nav.statistics"))
        self.btn_miesiac.setText(t("stats.this_month"))
        self.btn_rok.setText(t("stats.this_year"))
        for klucz, etykieta in self.etykiety:
            etykieta.setText(t("stats." + klucz))
        for klucz, (tytul, _, _) in self.karty.items():
            tytul.setText(t("stats." + klucz))
        for indeks, klucz in enumerate(self.tabele):
            self.zakladki.setTabText(indeks, t("stats." + klucz))

        for pole, opcje in (
            (self.podstawa, (("stats.service", "usluga"), ("stats.payment", "platnosc"))),
            (self.grupowanie, (("stats.monthly", "miesiac"), ("stats.yearly", "rok"))),
            (self.status, (("stats.all", None), ("stats.paid", "oplacony"),
                           ("stats.unpaid", "do_zaplaty"))),
        ):
            self._opcje(pole, [(t(klucz), wartosc) for klucz, wartosc in opcje])

    def odswiez(self) -> None:
        kategorie, dostawcy = StatystykiRachunkow(self.rejestr.db).opcje_filtrow()
        self.nazwy_kategorii = {ident: category_name(nazwa) for ident, nazwa in kategorie.items()}
        self.nazwy_kategorii[BEZ_KATEGORII] = t("stats.uncategorized")
        self._opcje(self.kategoria, [(t("stats.all"), None), *(
            (nazwa, ident) for ident, nazwa in self.nazwy_kategorii.items()
        )])
        self._opcje(self.dostawca, [(t("stats.all"), None), *((n, n) for n in dostawcy)])
        self._oblicz()

    def _zmien_podstawe(self) -> None:
        platnosc = self.podstawa.currentData() == "platnosc"
        if platnosc:
            self.status_uslugi = self.status.currentData()
        with QSignalBlocker(self.status):
            self.status.setCurrentIndex(self.status.findData(
                "oplacony" if platnosc else self.status_uslugi
            ))
        self.status.setEnabled(not platnosc)
        self._oblicz()

    def _oblicz(self) -> None:
        od, do = self.od.date().toPython(), self.do.date().toPython()
        podstawa = self.podstawa.currentData()
        opis = t("stats.hint." + podstawa)
        if self.kategoria.currentData() is not None:
            opis += " " + t("stats.hint.category")
        self.opis_podstawy.setText(opis)
        if od > do:
            for _, wartosc, opis in self.karty.values():
                wartosc.setText("—")
                opis.clear()
            self.porownanie.clear()
            self.komunikat.setText(t("stats.invalid_range"))
            self.komunikat.show()
            self.zakladki.hide()
            return

        grupowanie = self.grupowanie.currentData()
        raport = StatystykiRachunkow(self.rejestr.db).zestawienie(
            ZakresDat(od, do), podstawa=podstawa, grupowanie=grupowanie,
            kategoria=self.kategoria.currentData(), dostawca=self.dostawca.currentData(),
            status=self.status.currentData(),
        )
        self._pokaz_podsumowanie(raport)
        self.komunikat.setText(t("stats.empty"))
        self.komunikat.setVisible(raport.biezacy.liczba == 0)
        self.zakladki.setVisible(raport.biezacy.liczba > 0)
        self._wypelnij("periods", sorted(raport.okresy.items()), t("stats." + grupowanie))
        self._wypelnij("categories", sorted(
            ((self.nazwy_kategorii.get(ident, str(ident)), suma)
             for ident, suma in raport.kategorie.items()),
            key=lambda w: (-w[1].razem, w[0].casefold()),
        ), t("stats.category"), raport.biezacy.razem)
        self._wypelnij("suppliers", sorted(
            raport.dostawcy.items(), key=lambda w: (-w[1].razem, w[0].casefold())
        ), t("stats.supplier"), raport.biezacy.razem)

    def _pokaz_podsumowanie(self, raport: Zestawienie) -> None:
        aktualny = raport.biezacy
        for klucz, kwota in (
            ("total", aktualny.razem), ("paid", aktualny.oplacone), ("unpaid", aktualny.do_zaplaty),
        ):
            self.karty[klucz][1].setText(_kwota(kwota))
        self.karty["total"][2].setText(t("dashboard.invoice_count", count=aktualny.liczba))
        poprzedni = raport.poprzedni_zakres
        _, wartosc, opis = self.karty["comparison"]
        if poprzedni is None:
            wartosc.setText("—")
            opis.clear()
            self.porownanie.clear()
            return
        wartosc.setText(_kwota(raport.poprzedni.razem))
        opis.setText(f"{poprzedni.od} – {poprzedni.do}")
        roznica = aktualny.razem - raport.poprzedni.razem
        zmiana = ("+" if roznica > 0 else "") + _kwota(roznica)
        self.porownanie.setText(t("stats.change", amount=zmiana))

    def _wypelnij(
        self, klucz: str, wiersze: list[tuple[str, Suma]], etykieta: str, total: int | None = None,
    ) -> None:
        tabela = self.tabele[klucz]
        naglowki = [etykieta, t("stats.chart"), t("stats.total"), t("stats.paid"), t("stats.unpaid")]
        if total is not None:
            naglowki.append(t("stats.share"))
        tabela.setColumnCount(len(naglowki))
        tabela.setHorizontalHeaderLabels(naglowki)
        header = tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tabela.setColumnWidth(0, 180)
        tabela.setRowCount(0)
        tabela.setRowCount(len(wiersze))
        maksimum = max((s.razem for _, s in wiersze), default=0)
        for i, (nazwa, suma) in enumerate(wiersze):
            etykieta_wiersza = QTableWidgetItem(nazwa)
            etykieta_wiersza.setToolTip(nazwa)
            tabela.setItem(i, 0, etykieta_wiersza)
            slupek = QProgressBar()
            slupek.setObjectName("slupekStatystyk")
            slupek.setRange(0, 1000)
            slupek.setValue((1000 * suma.razem) // maksimum if maksimum else 0)
            slupek.setTextVisible(False)
            slupek.setAccessibleName(f"{nazwa} · {_kwota(suma.razem)}")
            slupek.setToolTip(_kwota(suma.razem))
            slupek.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tabela.setCellWidget(i, 1, slupek)
            tekst = [_kwota(kwota) for kwota in (suma.razem, suma.oplacone, suma.do_zaplaty)]
            if total is not None:
                udzial = f"{100 * suma.razem / total:.1f}%" if total else "0%"
                tekst.append(udzial.replace(".", ",") if current_language() == "pl" else udzial)
            for kolumna, wartosc in enumerate(tekst, 2):
                pozycja = QTableWidgetItem(wartosc)
                pozycja.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tabela.setItem(i, kolumna, pozycja)


def _kwota(grosze: int) -> str:
    znak = "−" if grosze < 0 else ""
    return f"{znak}{grosze_na_kwote(abs(grosze))} {t('invoices.currency')}"
