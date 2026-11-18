# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Edycja i podsumowanie danych faktury."""
from __future__ import annotations

import sqlite3
from typing import NamedTuple

from PySide6.QtCore import QObject, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from i18n import category_name, t
from uslugi.rachunki import RejestrRachunkow, grosze_na_kwote


class StanFormularza(NamedTuple):
    dostawca: str
    numer: str
    numer_konta: str
    kwota: str
    kategoria_id: int | None
    wystawiono: str
    termin: str
    okres_od: str
    okres_do: str
    status: str
    uwagi: str
    oplacono: str


class FormularzFaktury(QObject):
    """Widoki edycji i podsumowania, akcje użytkownika i stan formularza."""

    podsumowanie_zadane = Signal()
    edycja_zadana = Signal()
    wybor_kategorii = Signal()
    zapis_zadany = Signal()
    wzorzec_zadany = Signal()

    _FORM_KEYS = (
        "form.supplier", "form.invoice", "form.account", "form.amount",
        "form.category", "form.issued", "form.due", "form.period_from",
        "form.period_to", "form.status", "form.paid_date", "form.notes",
    )

    def __init__(self, rejestr: RejestrRachunkow, parent: QWidget):
        super().__init__(parent)
        self.rejestr = rejestr
        self._nazwa_pliku: str | None = None
        self._klucz_podsumowania = "invoice.no_document"
        self._aktualizacja_wzorca = False
        self.edycja = self._zbuduj_formularz()
        self.podsumowanie = self._zbuduj_fakture()
        self.odswiez_kategorie()
        self.ustaw_zapis_aktywny(False)

    def _zbuduj_formularz(self) -> QWidget:
        przewijanie = QScrollArea()
        przewijanie.setWidgetResizable(True)
        przewijanie.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(10, 14, 10, 12)
        uklad.setSpacing(10)
        self.nazwa_dokumentu = QLabel()
        self.nazwa_dokumentu.setWordWrap(True)
        uklad.addWidget(self.nazwa_dokumentu)
        forma = QFormLayout()
        forma.setSpacing(8)

        self.ed_dostawca = QLineEdit()
        self.ed_numer = QLineEdit()
        self.ed_konto = QLineEdit()
        self.ed_kwota = QLineEdit()
        self.ed_wystawiono = QLineEdit()
        self.ed_termin = QLineEdit()
        self.ed_od = QLineEdit()
        self.ed_do = QLineEdit()
        self.wybor_kategoria = QComboBox()
        wybor_i_dodaj = QWidget()
        kategoria_uklad = QHBoxLayout(wybor_i_dodaj)
        kategoria_uklad.setContentsMargins(0, 0, 0, 0)
        kategoria_uklad.addWidget(self.wybor_kategoria, 1)
        dodaj = QPushButton("+")
        self.btn_dodaj_kategorie = dodaj
        dodaj.clicked.connect(self.wybor_kategorii)
        kategoria_uklad.addWidget(dodaj)

        self.wybor_status = QComboBox()
        self.wybor_status.addItem("", "do_zaplaty")
        self.wybor_status.addItem("", "oplacony")
        self.ed_oplacono = QLineEdit()
        self.ed_oplacono.setEnabled(False)
        self.wybor_status.currentIndexChanged.connect(self._zmiana_statusu_platnosci)
        self.ed_uwagi = QTextEdit()
        self.ed_uwagi.setMaximumHeight(86)

        self._form_labels = []
        for element in (
            self.ed_dostawca,
            self.ed_numer,
            self.ed_konto,
            self.ed_kwota,
            wybor_i_dodaj,
            self.ed_wystawiono,
            self.ed_termin,
            self.ed_od,
            self.ed_do,
            self.wybor_status,
            self.ed_oplacono,
            self.ed_uwagi,
        ):
            etykieta = QLabel()
            forma.addRow(etykieta, element)
            self._form_labels.append(etykieta)
        uklad.addLayout(forma)
        self.btn_przejdz_faktura = QPushButton()
        self.btn_przejdz_faktura.clicked.connect(self.podsumowanie_zadane)
        uklad.addWidget(self.btn_przejdz_faktura)
        komunikat = QLabel()
        self.tekst_ostrzezenia_form = komunikat
        komunikat.setWordWrap(True)
        komunikat.setObjectName("podpowiedz")
        uklad.addWidget(komunikat)
        uklad.addStretch()
        przewijanie.setWidget(panel)
        return przewijanie

    def _zbuduj_fakture(self) -> QWidget:
        """Podsumowanie faktury — osobny, świadomy etap zapisu do SQLite."""
        przewijanie = QScrollArea()
        przewijanie.setWidgetResizable(True)
        przewijanie.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(14, 16, 14, 14)
        uklad.setSpacing(12)
        self.tytul_faktury = QLabel()
        self.tytul_faktury.setStyleSheet("font-size: 20px; font-weight: 700;")
        uklad.addWidget(self.tytul_faktury)
        self.info_faktury = QLabel()
        self.info_faktury.setWordWrap(True)
        self.info_faktury.setObjectName("podpowiedz")
        uklad.addWidget(self.info_faktury)

        podsumowanie = QFormLayout()
        podsumowanie.setSpacing(12)
        self.podsumowanie_wartosci = {}
        self.podsumowanie_etykiety = {}
        pola = (
            ("form.supplier", "dostawca"), ("form.invoice", "numer"),
            ("form.account", "konto"), ("form.amount", "kwota"),
            ("form.category", "kategoria"), ("form.issued", "wystawiono"),
            ("form.due", "termin"), ("form.period_from", "od"),
            ("form.period_to", "do"), ("form.status", "status"),
            ("form.paid_date", "oplacono"), ("form.notes", "uwagi"),
        )
        for klucz, pole in pola:
            etykieta = QLabel()
            wartosc = QLabel("—")
            wartosc.setWordWrap(True)
            wartosc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            podsumowanie.addRow(etykieta, wartosc)
            self.podsumowanie_wartosci[pole] = wartosc
            self.podsumowanie_etykiety[klucz] = etykieta
        uklad.addLayout(podsumowanie)

        self.btn_powrot_edycja = QPushButton()
        self.btn_powrot_edycja.clicked.connect(self.edycja_zadana)
        uklad.addWidget(self.btn_powrot_edycja)

        self.zapisz_przycisk = QPushButton()
        self.zapisz_przycisk.setObjectName("zapiszFakture")
        self.zapisz_przycisk.clicked.connect(self.zapis_zadany)
        uklad.addWidget(self.zapisz_przycisk)
        self.info_propozycji_wzorca = QLabel()
        self.info_propozycji_wzorca.setWordWrap(True)
        self.info_propozycji_wzorca.setObjectName("podpowiedz")
        self.info_propozycji_wzorca.hide()
        uklad.addWidget(self.info_propozycji_wzorca)
        self.btn_proponuj_wzorzec = QPushButton()
        self.btn_proponuj_wzorzec.clicked.connect(self.wzorzec_zadany)
        self.btn_proponuj_wzorzec.hide()
        uklad.addWidget(self.btn_proponuj_wzorzec)
        uklad.addStretch()
        przewijanie.setWidget(panel)
        return przewijanie

    def przetlumacz(self) -> None:
        self.zapisz_przycisk.setText(t("button.save"))
        self.tekst_ostrzezenia_form.setText(t("form.hint"))
        for label, key in zip(self._form_labels, self._FORM_KEYS):
            label.setText(t(key))
        self.ed_konto.setPlaceholderText(t("form.placeholder_account"))
        self.ed_kwota.setPlaceholderText(t("form.placeholder_amount"))
        for field in (self.ed_termin, self.ed_od, self.ed_do):
            field.setPlaceholderText(t("form.placeholder_date"))
        for field in (self.ed_wystawiono, self.ed_oplacono):
            field.setPlaceholderText(t("form.placeholder_required_date"))
        self.ed_uwagi.setPlaceholderText(t("form.placeholder_notes"))
        self.wybor_status.setItemText(0, t("form.status_due"))
        self.wybor_status.setItemText(1, t("form.status_paid"))
        self.wybor_kategoria.setItemText(0, t("form.choose_category"))
        self._localize_categories()
        self.btn_przejdz_faktura.setText(t("button.review_invoice"))
        self.btn_powrot_edycja.setText(t("button.back_to_edit"))
        self.tytul_faktury.setText(t("invoice.title"))
        for key, label in self.podsumowanie_etykiety.items():
            label.setText(t(key))
        self.btn_dodaj_kategorie.setToolTip(t("categories.open"))
        self._odswiez_nazwe_pliku()
        self._odswiez_wartosci_podsumowania()
        self.info_faktury.setText(t(self._klucz_podsumowania))
        self._odswiez_tekst_propozycji()

    def odswiez_podsumowanie(self, *, dokument: bool) -> None:
        self._odswiez_wartosci_podsumowania()
        self._pokaz_komunikat_podsumowania("invoice.review" if dokument else "invoice.no_document")

    def oznacz_zapisana(self, *, aktualizacja_wzorca: bool) -> None:
        self._odswiez_wartosci_podsumowania()
        self._pokaz_komunikat_podsumowania("invoice.saved")
        self.ustaw_tryb_propozycji_wzorca(aktualizacja_wzorca)
        self.info_propozycji_wzorca.show()
        self.btn_proponuj_wzorzec.show()

    def ustaw_tryb_propozycji_wzorca(self, aktualizacja: bool) -> None:
        self._aktualizacja_wzorca = aktualizacja
        self._odswiez_tekst_propozycji()

    def ukryj_propozycje_wzorca(self) -> None:
        self.info_propozycji_wzorca.hide()
        self.btn_proponuj_wzorzec.hide()

    def _odswiez_tekst_propozycji(self) -> None:
        self.btn_proponuj_wzorzec.setText(t(
            "patterns.propose_update" if self._aktualizacja_wzorca else "patterns.propose"
        ))
        self.info_propozycji_wzorca.setText(t(
            "patterns.offer_update" if self._aktualizacja_wzorca else "patterns.offer_new"
        ))

    def _pokaz_komunikat_podsumowania(self, klucz: str) -> None:
        self._klucz_podsumowania = klucz
        self.info_faktury.setText(t(klucz))

    def _odswiez_wartosci_podsumowania(self) -> None:
        wartosci = {
            "dostawca": self.ed_dostawca.text(),
            "numer": self.ed_numer.text(),
            "konto": self.ed_konto.text(),
            "kwota": self.ed_kwota.text(),
            "kategoria": self._nazwa_wybranej_kategorii() or "",
            "wystawiono": self.ed_wystawiono.text(),
            "termin": self.ed_termin.text(),
            "od": self.ed_od.text(),
            "do": self.ed_do.text(),
            "status": self.wybor_status.currentText(),
            "oplacono": self.ed_oplacono.text() if self.ed_oplacono.isEnabled() else "",
            "uwagi": self.ed_uwagi.toPlainText(),
        }
        for pole, wartosc in wartosci.items():
            self.podsumowanie_wartosci[pole].setText(wartosc.strip() or "—")

    def wczytaj_dokument(self, nazwa_pliku: str, zapis: sqlite3.Row | None) -> None:
        self._nazwa_pliku = nazwa_pliku
        self._odswiez_nazwe_pliku()
        self._wyczysc_pola()
        if zapis is not None:
            self._wczytaj_rachunek(zapis)
        self.ustaw_zapis_aktywny(zapis is None or zapis["wycofano_utc"] is None)

    def _odswiez_nazwe_pliku(self) -> None:
        if self._nazwa_pliku is None:
            self.nazwa_dokumentu.setText(t("doc.import_first"))
        else:
            self.nazwa_dokumentu.setText(t("doc.original", name=self._nazwa_pliku))

    def _wczytaj_rachunek(self, zapis: sqlite3.Row) -> None:
        self.ed_dostawca.setText(zapis["dostawca"])
        self.ed_numer.setText(zapis["numer"])
        self.ed_konto.setText(zapis["numer_konta"])
        self.ed_kwota.setText(grosze_na_kwote(zapis["kwota_grosze"]))
        self.ed_wystawiono.setText(zapis["data_wystawienia"] or "")
        self.ed_termin.setText(zapis["termin_platnosci"] or "")
        self.ed_od.setText(zapis["okres_od"] or "")
        self.ed_do.setText(zapis["okres_do"] or "")
        self.ed_uwagi.setPlainText(zapis["uwagi"])
        self.odswiez_kategorie(zapis["kategoria_id"])
        self.wczytaj_platnosc(zapis)

    def _wyczysc_pola(self) -> None:
        for pole in (self.ed_dostawca, self.ed_numer, self.ed_konto, self.ed_kwota, self.ed_wystawiono,
                     self.ed_termin, self.ed_od, self.ed_do):
            pole.clear()
        self.ed_uwagi.clear()
        self.wybor_status.setCurrentIndex(0)
        self.ed_oplacono.clear()
        self.odswiez_kategorie()

    def wypelnij_z_analizy(self, sugestie: dict[str, str]) -> None:
        """Uzupełnij pola zaakceptowanymi sugestiami analizy."""
        pola = {
            "dostawca": self.ed_dostawca,
            "numer_faktury": self.ed_numer,
            "kwota_do_zaplaty": self.ed_kwota,
            "data_wystawienia": self.ed_wystawiono,
            "termin_platnosci": self.ed_termin,
            "okres_od": self.ed_od,
            "okres_do": self.ed_do,
            "numer_konta_bankowego": self.ed_konto,
        }
        for pole, kontrolka in pola.items():
            if pole in sugestie:
                kontrolka.setText(sugestie[pole])
        if "kategoria_sugerowana" in sugestie:
            nazwa = sugestie["kategoria_sugerowana"]
            identyfikator = next(
                (int(row["id"]) for row in self.rejestr.kategorie() if row["nazwa"] == nazwa),
                None,
            )
            self._wybierz_kategorie(identyfikator)

    def wypelnij_z_qr(self, *, kwota_grosze: int, numer_konta: str) -> None:
        self.ed_kwota.setText(grosze_na_kwote(kwota_grosze))
        self.ed_konto.setText(numer_konta)

    def dane_do_wzorca(self) -> tuple[str, str | None]:
        return self.ed_dostawca.text(), self._nazwa_wybranej_kategorii()

    def _nazwa_wybranej_kategorii(self) -> str | None:
        if self.wybor_kategoria.currentData() is None:
            return None
        return self.wybor_kategoria.currentText()

    def ustaw_zapis_aktywny(self, aktywny: bool) -> None:
        self.zapisz_przycisk.setEnabled(aktywny)

    def ustaw_fokus_daty(self, *, wystawienia: bool) -> None:
        pole = self.ed_wystawiono if wystawienia else self.ed_oplacono
        pole.setFocus()

    def stan(self) -> StanFormularza:
        return StanFormularza(
            dostawca=self.ed_dostawca.text(),
            numer=self.ed_numer.text(),
            numer_konta=self.ed_konto.text(),
            kwota=self.ed_kwota.text(),
            kategoria_id=self.wybor_kategoria.currentData(),
            wystawiono=self.ed_wystawiono.text(),
            termin=self.ed_termin.text(),
            okres_od=self.ed_od.text(),
            okres_do=self.ed_do.text(),
            status=self.wybor_status.currentData(),
            uwagi=self.ed_uwagi.toPlainText(),
            oplacono=self.ed_oplacono.text(),
        )

    def odswiez_kategorie(self, wybrana: int | None = None) -> None:
        self.wybor_kategoria.clear()
        self.wybor_kategoria.addItem(t("form.choose_category"), None)
        for wiersz in self.rejestr.kategorie():
            self.wybor_kategoria.addItem(wiersz["nazwa"], int(wiersz["id"]))
        self._localize_categories()
        self._wybierz_kategorie(wybrana)

    def _wybierz_kategorie(self, identyfikator: int | None) -> None:
        numer = self.wybor_kategoria.findData(identyfikator)
        if numer >= 0:
            self.wybor_kategoria.setCurrentIndex(numer)

    def wczytaj_platnosc(self, zapis: sqlite3.Row) -> None:
        with QSignalBlocker(self.wybor_status):
            self.wybor_status.setCurrentIndex(self.wybor_status.findData(zapis["status"]))
        self.ed_oplacono.setEnabled(zapis["status"] == "oplacony")
        self.ed_oplacono.setText(zapis["data_oplacenia"] or "")

    def _zmiana_statusu_platnosci(self) -> None:
        oplacony = self.wybor_status.currentData() == "oplacony"
        self.ed_oplacono.setEnabled(oplacony)

    def _localize_categories(self) -> None:
        # Only display labels change. IDs and DB names remain untouched.
        by_id = {int(row["id"]): row["nazwa"] for row in self.rejestr.kategorie()}
        for i in range(1, self.wybor_kategoria.count()):
            category_id = self.wybor_kategoria.itemData(i)
            original_name = by_id.get(category_id)
            if original_name is not None:
                self.wybor_kategoria.setItemText(i, category_name(original_name))
