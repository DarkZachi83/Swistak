# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Tabela zapisanych faktur; archiwum wszystkich PDF pozostaje osobnym widokiem."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ai_core.hybrid import today_warsaw
from gui.uklad import Siatka
from i18n import category_name, t
from uslugi.rachunki import RejestrRachunkow, grosze_na_kwote

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
STATUS_ROLE = Qt.ItemDataRole.UserRole + 2
AMOUNT_ROLE = Qt.ItemDataRole.UserRole + 3
DUE_ROLE = Qt.ItemDataRole.UserRole + 4


class KomorkaFaktury(QTableWidgetItem):
    """Sortuj po wartości danych, nie po sformatowanym tekście."""
    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, KomorkaFaktury):
            a = self.data(SORT_ROLE)
            b = other.data(SORT_ROLE)
            if a is not None and b is not None:
                return a < b
        return super().__lt__(other)


class TabelaFaktur(QWidget):
    """Widok read-only; otwarcie faktury deleguje do głównego okna."""
    otworz_dokument = Signal(int)

    KOLUMNY = (
        "invoices.supplier", "invoices.number", "invoices.issued",
        "invoices.due", "invoices.amount", "invoices.category",
        "invoices.status", "invoices.pdf",
    )

    def __init__(self, rejestr: RejestrRachunkow):
        super().__init__()
        self.rejestr = rejestr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(10)

        self.tytul = QLabel()
        self.tytul.setObjectName("pulpitTytul")
        layout.addWidget(self.tytul)
        self.wskazowka = QLabel()
        self.wskazowka.setWordWrap(True)
        self.wskazowka.setObjectName("podpowiedz")
        layout.addWidget(self.wskazowka)

        filters = Siatka(4, szerokosc=150)
        self.szukaj = QLineEdit()
        self.szukaj.setObjectName("szukajFaktur")
        self.szukaj.setClearButtonEnabled(True)
        self.szukaj.textChanged.connect(self._filtruj)
        filters.dodaj(self.szukaj)

        self.filtr_status = QComboBox()
        self.filtr_status.addItem("", None)
        self.filtr_status.addItem("", "do_zaplaty")
        self.filtr_status.addItem("", "oplacony")
        self.filtr_status.currentIndexChanged.connect(self._filtruj)
        filters.dodaj(self.filtr_status)

        self.filtr_terminu = QComboBox()
        for value in (None, "overdue", "due_soon"):
            self.filtr_terminu.addItem("", value)
        self.filtr_terminu.currentIndexChanged.connect(self._filtruj)
        filters.dodaj(self.filtr_terminu)

        self.btn_odswiez = QPushButton()
        self.btn_odswiez.clicked.connect(self.odswiez)
        filters.dodaj(self.btn_odswiez)
        layout.addWidget(filters)

        self.tabela = QTableWidget(0, len(self.KOLUMNY))
        self.tabela.setObjectName("tabelaFaktur")
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.tabela.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate((180, 135, 110, 110, 105, 145, 105, 180)):
            self.tabela.setColumnWidth(index, width)
        self.tabela.setSortingEnabled(True)
        self.tabela.sortItems(2, Qt.SortOrder.DescendingOrder)
        self.tabela.itemSelectionChanged.connect(self._zmieniono_wybor)
        self.tabela.itemDoubleClicked.connect(self._otworz_wybrana)
        layout.addWidget(self.tabela, 1)

        footer = QHBoxLayout()
        self.podsumowanie = QLabel()
        self.podsumowanie.setWordWrap(True)
        self.podsumowanie.setObjectName("podpowiedz")
        footer.addWidget(self.podsumowanie, 1)
        self.btn_otworz = QPushButton()
        self.btn_otworz.clicked.connect(self._otworz_wybrana)
        footer.addWidget(self.btn_otworz)
        layout.addLayout(footer)
        self.przetlumacz()

    def wybrane_dokument_id(self) -> int | None:
        row = self.tabela.currentRow()
        if row < 0 or self.tabela.isRowHidden(row):
            return None
        item = self.tabela.item(row, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _zmieniono_wybor(self) -> None:
        self.btn_otworz.setEnabled(self.wybrane_dokument_id() is not None)

    def _otworz_wybrana(self, *_args) -> None:
        dokument_id = self.wybrane_dokument_id()
        if dokument_id is not None:
            self.otworz_dokument.emit(dokument_id)

    def odswiez(self) -> None:
        """Odczytaj stan SQLite bez naruszania filtra, sortowania i wyboru."""
        selected = self.wybrane_dokument_id()
        header = self.tabela.horizontalHeader()
        sort_column, sort_order = header.sortIndicatorSection(), header.sortIndicatorOrder()
        rows = self.rejestr.faktury()
        self.tabela.setSortingEnabled(False)
        self.tabela.setRowCount(0)
        self.tabela.setRowCount(len(rows))
        for row, invoice in enumerate(rows):
            amount = int(invoice["kwota_grosze"])
            status = str(invoice["status"])
            shown = (
                str(invoice["dostawca"]), str(invoice["numer"] or "—"),
                str(invoice["data_wystawienia"] or "—"),
                str(invoice["termin_platnosci"] or "—"),
                grosze_na_kwote(amount) + " " + t("invoices.currency"),
                category_name(invoice["kategoria"]) if invoice["kategoria"] else "—",
                t("form.status_paid" if status == "oplacony" else "form.status_due"),
                str(invoice["nazwa_zrodlowa"]),
            )
            keys = (
                shown[0].casefold(), shown[1].casefold(),
                invoice["data_wystawienia"] or "",
                invoice["termin_platnosci"] or "",
                amount, shown[5].casefold(), shown[6].casefold(),
                shown[7].casefold(),
            )
            for column, (value, key) in enumerate(zip(shown, keys)):
                item = KomorkaFaktury(value)
                item.setData(SORT_ROLE, key)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(invoice["dokument_id"]))
                    item.setData(STATUS_ROLE, status)
                    item.setData(AMOUNT_ROLE, amount)
                    item.setData(DUE_ROLE, invoice["termin_platnosci"])
                self.tabela.setItem(row, column, item)
        self.tabela.setSortingEnabled(True)
        if sort_column < 0 or sort_column >= len(self.KOLUMNY):
            sort_column, sort_order = 2, Qt.SortOrder.DescendingOrder
        self.tabela.sortItems(sort_column, sort_order)
        if selected is not None:
            for row in range(self.tabela.rowCount()):
                item = self.tabela.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected:
                    self.tabela.selectRow(row)
                    break
        self._filtruj()
        self._zmieniono_wybor()

    def _filtruj(self, *_args) -> None:
        phrase = " ".join(self.szukaj.text().casefold().split())
        status_filter = self.filtr_status.currentData()
        termin = self.filtr_terminu.currentData()
        dzis = today_warsaw()
        do = (date.fromisoformat(dzis) + timedelta(days=7)).isoformat()
        shown = 0
        total_grosze = 0
        for row in range(self.tabela.rowCount()):
            first = self.tabela.item(row, 0)
            if first is None:
                continue
            status = first.data(STATUS_ROLE)
            text = " ".join(
                self.tabela.item(row, col).text().casefold()
                for col in range(len(self.KOLUMNY))
            )
            ok = (not status_filter or status_filter == status) and phrase in text
            if termin:
                termin_platnosci = first.data(DUE_ROLE)
                w_terminie = bool(termin_platnosci and (
                    termin_platnosci < dzis if termin == "overdue" else dzis <= termin_platnosci <= do
                ))
                ok = ok and status == "do_zaplaty" and w_terminie
            self.tabela.setRowHidden(row, not ok)
            if ok:
                shown += 1
                total_grosze += int(first.data(AMOUNT_ROLE))
        if self.wybrane_dokument_id() is None:
            self.tabela.clearSelection()
        self.podsumowanie.setText(t(
            "invoices.summary", shown=shown, total=self.tabela.rowCount(),
            amount=grosze_na_kwote(total_grosze),
        ))
        self._zmieniono_wybor()

    def przetlumacz(self) -> None:
        self.tytul.setText(t("nav.invoices"))
        self.wskazowka.setText(t("invoices.hint"))
        self.szukaj.setPlaceholderText(t("invoices.search"))
        self.filtr_status.setItemText(0, t("invoices.all_statuses"))
        self.filtr_status.setItemText(1, t("form.status_due"))
        self.filtr_status.setItemText(2, t("form.status_paid"))
        self.filtr_terminu.setItemText(0, t("invoices.all_due_dates"))
        self.filtr_terminu.setItemText(1, t("dashboard.overdue"))
        self.filtr_terminu.setItemText(2, t("dashboard.due_soon"))
        self.btn_odswiez.setText(t("button.refresh"))
        self.btn_otworz.setText(t("invoices.open"))
        self.tabela.setHorizontalHeaderLabels([t(key) for key in self.KOLUMNY])
        self.odswiez()

    def pokaz_naleznosci(self, zakres: str) -> None:
        self.szukaj.clear()
        self.filtr_status.setCurrentIndex(self.filtr_status.findData("do_zaplaty"))
        self.filtr_terminu.setCurrentIndex(max(0, self.filtr_terminu.findData(zakres)))
