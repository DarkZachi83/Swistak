# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 6: Plan rachunków, Historia i miesięczne zamykanie.

Dialog jest warstwą świadomych działań użytkownika. Żadna sugestia LLM
nie wywołuje tu operacji zapisu bez kliknięcia, potwierdzenia i walidacji.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QFormLayout, QHeaderView, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QInputDialog,
)

from i18n import t
from uslugi.finanse import Finanse, cykl_miesiaca
from uslugi.historia import HistoriaRozliczen
from uslugi.plan_rachunkow import PlanRachunkow
from uslugi.rachunki import RejestrRachunkow, grosze_na_kwote

ID_ROLE = Qt.ItemDataRole.UserRole


def now_pl() -> datetime:
    return datetime.now(ZoneInfo("Europe/Warsaw"))


def table_widget(headers: tuple[str, ...], name: str) -> QTableWidget:
    widget = QTableWidget(0, len(headers))
    widget.setObjectName(name)
    widget.setHorizontalHeaderLabels([t(k) for k in headers])
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setAlternatingRowColors(True)
    widget.verticalHeader().setVisible(False)
    widget.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def set_rows(table: QTableWidget, rows: list[tuple[object, ...]],
             ids: list[int]) -> None:
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for rownum, (values, ident) in enumerate(zip(rows, ids)):
        for col, val in enumerate(values):
            item = QTableWidgetItem(str(val) if val is not None else "—")
            if col == 0:
                item.setData(ID_ROLE, ident)
            table.setItem(rownum, col, item)
    table.setSortingEnabled(True)


def chosen_id(table: QTableWidget) -> int | None:
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    return int(item.data(ID_ROLE)) if item is not None else None


def confirm(parent: QWidget, title: str, text: str) -> bool:
    return QMessageBox.question(
        parent, title, text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    ) == QMessageBox.StandardButton.Yes


class FormularzProfilu(QDialog):
    """Formularz nowego profilu lub nowej, przyszłej wersji harmonogramu."""

    def __init__(self, categories: list[dict], profile: dict | None = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("formularzPlanu")
        self.setWindowTitle(t("plan.schedule.edit") if profile else t("plan.profile.create"))
        self.profile = profile
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(profile["nazwa"] if profile else "")
        self.name.setObjectName("planProfileName")
        form.addRow(t("plan.profile.name"), self.name)
        self.supplier = QLineEdit(profile["dostawca"] if profile else "")
        form.addRow(t("plan.profile.supplier"), self.supplier)
        self.category = QComboBox()
        self.category.addItem(t("plan.profile.no_category"), None)
        for category in categories:
            self.category.addItem(category["nazwa"], int(category["id"]))
        if profile and profile["kategoria_id"] is not None:
            index = self.category.findData(int(profile["kategoria_id"]))
            if index >= 0:
                self.category.setCurrentIndex(index)
        form.addRow(t("plan.profile.category"), self.category)
        self.type = QComboBox()
        for key in ("miesieczny","co_n_miesiecy","nieregularny"):
            self.type.addItem(t("plan.type."+key),key)
        if profile:
            self.type.setCurrentIndex(self.type.findData(profile["typ"]))
        form.addRow(t("plan.profile.frequency"),self.type)
        self.every = QSpinBox()
        self.every.setRange(1,120)
        self.every.setValue(int(profile["co_ile_miesiecy"]) if profile else 1)
        self.every.setObjectName("planFrequency")
        form.addRow(t("plan.profile.every"),self.every)
        today=now_pl().strftime("%Y-%m")
        self.start = QLineEdit(today if profile is None else today)
        self.start.setObjectName("planStartMonth")
        form.addRow(t("plan.profile.from"),self.start)
        self.anchor = QLineEdit(
            profile["cykl_kotwicy"] if profile else today
        )
        self.anchor.setObjectName("planAnchorMonth")
        form.addRow(t("plan.profile.anchor"),self.anchor)
        self.delay = QSpinBox()
        self.delay.setRange(-62,180)
        self.delay.setValue(int(profile["przesuniecie_dni"]) if profile else 0)
        form.addRow(t("plan.profile.delay"),self.delay)
        layout.addLayout(form)
        self.help = QLabel(t("plan.profile.hint"))
        self.help.setWordWrap(True)
        layout.addWidget(self.help)
        if profile:
            self.name.setReadOnly(True)
            self.supplier.setReadOnly(True)
            self.category.setEnabled(False)
        self.type.currentIndexChanged.connect(self._frequency)
        self._frequency()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(t("plan.apply"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("plan.cancel"))
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _frequency(self, *_args):
        self.every.setEnabled(self.type.currentData()=="co_n_miesiecy")
        if self.type.currentData()=="miesieczny":
            self.every.setValue(1)

    def values(self) -> dict:
        return {
            "nazwa": self.name.text().strip(),
            "dostawca": self.supplier.text().strip(),
            "kategoria_id": self.category.currentData(),
            "typ": self.type.currentData(),
            "co_ile_miesiecy": self.every.value() if self.type.currentData()=="co_n_miesiecy" else 1,
            "cykl_od": self.start.text().strip(),
            "cykl_kotwicy": self.anchor.text().strip(),
            "przesuniecie_dni": self.delay.value(),
        }

    def _validate(self):
        values = self.values()
        try:
            cykl_miesiaca(values["cykl_od"])
            cykl_miesiaca(values["cykl_kotwicy"])
            if not values["nazwa"]:
                raise ValueError(t("plan.profile.name_required"))
            if self.profile and values["cykl_od"] <= self.profile["cykl_od"]:
                raise ValueError(t("plan.schedule.future_required"))
        except ValueError as error:
            QMessageBox.warning(self, t("plan.title"), str(error))
            return
        self.accept()


class DialogPlanHistoria(QDialog):
    """Jedno miejsce obsługi Plan / Historia / Zamknięcie miesiąca."""

    daneZmienione = Signal(object)  # id faktury lub None: analiza całego zakresu

    def __init__(self, rejestr: RejestrRachunkow, parent=None):
        super().__init__(parent)
        self.setObjectName("dialogPlanHistoria")
        self.setWindowTitle(t("plan.title"))
        self.resize(1080,790)
        self.setMinimumSize(820,600)
        self.rejestr = rejestr
        self.plan = PlanRachunkow(rejestr.db)
        self.finanse = Finanse(rejestr.db)
        self.history = HistoriaRozliczen(rejestr.db)
        self._loading = False
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(t("plan.month")))
        self.month = QComboBox()
        self.month.setEditable(True)
        self.month.setObjectName("planSelectedMonth")
        top.addWidget(self.month,1)
        self.refresh_btn = QPushButton(t("plan.refresh"))
        self.refresh_btn.clicked.connect(self.refresh)
        top.addWidget(self.refresh_btn)
        outer.addLayout(top)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("planHistoryTabs")
        outer.addWidget(self.tabs,1)
        self._plan_tab()
        self._history_tab()
        self._closing_tab()
        self.month.currentTextChanged.connect(self._on_month_change)
        self.refresh()
        self.tabs.currentChanged.connect(self.refresh)

    def _plan_tab(self):
        pane=QWidget()
        layout=QVBoxLayout(pane)
        info=QLabel(t("plan.profiles.help"))
        info.setWordWrap(True)
        layout.addWidget(info)
        self.profiles = table_widget((
            "plan.col.name","plan.col.supplier","plan.col.category",
            "plan.col.type","plan.col.since","plan.col.state"
        ),"planProfileTable")
        layout.addWidget(self.profiles,2)
        buttons=QHBoxLayout()
        for key,slot,name in [
            ("plan.profile.create",self._create_profile,"planCreateProfile"),
            ("plan.schedule.edit",self._edit_schedule,"planEditSchedule"),
            ("plan.profile.toggle",self._toggle_profile,"planToggleProfile"),
        ]:
            button=QPushButton(t(key));button.setObjectName(name)
            button.clicked.connect(slot);buttons.addWidget(button)
        layout.addLayout(buttons)
        layout.addWidget(QLabel(t("plan.expected.title")))
        self.expected = table_widget((
            "plan.col.profile","plan.col.expected","plan.col.status",
            "plan.col.linked","plan.col.exception",
        ),"planExpectedTable")
        layout.addWidget(self.expected,2)
        actions=QHBoxLayout()
        for key,slot,name in [
            ("plan.generate",self._generate,"planGenerate"),
            ("plan.link",self._link,"planLink"),
            ("plan.unlink",self._unlink,"planUnlink"),
            ("plan.exception",self._set_exception,"planSetException"),
            ("plan.exception.cancel",self._clear_exception,"planClearException"),
        ]:
            button=QPushButton(t(key));button.setObjectName(name)
            button.clicked.connect(slot);actions.addWidget(button)
        layout.addLayout(actions)
        self.tabs.addTab(pane,t("plan.tab.plan"))

    def _history_tab(self):
        pane=QWidget()
        layout=QVBoxLayout(pane)
        self.history_summary=QLabel()
        self.history_summary.setObjectName("historySummary")
        self.history_summary.setWordWrap(True)
        layout.addWidget(self.history_summary)
        self.history_invoices=table_widget((
            "plan.col.supplier","plan.col.number","plan.col.amount",
            "plan.col.payment","plan.col.due","plan.col.paid",
            "plan.col.state",
        ),"historyInvoices")
        layout.addWidget(self.history_invoices,3)
        actions=QHBoxLayout()
        for key,slot,name in [
            ("history.mark_paid",self._paid,"historyMarkPaid"),
            ("history.revoke_paid",self._revoke_payment,"historyRevokePaid"),
            ("history.withdraw",self._withdraw,"historyWithdraw"),
            ("history.restore",self._restore,"historyRestore"),
        ]:
            button=QPushButton(t(key));button.setObjectName(name)
            button.clicked.connect(slot);actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(QLabel(t("history.audit.title")))
        self.audit=table_widget((
            "history.audit.time","history.audit.object",
            "history.audit.operation","history.audit.reason",
        ),"historyAudit")
        layout.addWidget(self.audit,2)
        self.tabs.addTab(pane,t("plan.tab.history"))

    def _closing_tab(self):
        pane=QWidget()
        layout=QVBoxLayout(pane)
        self.closure_status=QLabel()
        self.closure_status.setObjectName("closingSummary")
        self.closure_status.setWordWrap(True)
        layout.addWidget(self.closure_status)
        layout.addWidget(QLabel(t("closing.explanation")))
        self.close_expectations=table_widget((
            "plan.col.profile","plan.col.expected","plan.col.status",
            "plan.col.linked",
        ),"closingExpectedTable")
        layout.addWidget(self.close_expectations,1)
        self.empty_confirmation=QCheckBox(t("closing.empty_check"))
        self.empty_confirmation.setObjectName("confirmEmptyMonth")
        layout.addWidget(self.empty_confirmation)
        self.confirm_btn=QPushButton(t("closing.confirm"))
        self.confirm_btn.setObjectName("confirmMonthCompleteness")
        self.confirm_btn.clicked.connect(self._confirm_month)
        layout.addWidget(self.confirm_btn)
        self.tabs.addTab(pane,t("plan.tab.closure"))

    def _selected_month(self) -> str | None:
        value=self.month.currentText().strip()
        try:
            return cykl_miesiaca(value)
        except ValueError:
            return None

    def _on_month_change(self, *_args):
        if not self._loading:
            self._refresh_tables()

    def refresh(self, *_args):
        previous=self.month.currentText().strip()
        now=now_pl().strftime("%Y-%m")
        months=self.history.miesiace()
        if now not in months:
            months.insert(0,now)
        if previous and previous not in months:
            months.insert(0,previous)
        self._loading=True
        try:
            self.month.clear()
            self.month.addItems(months)
            self.month.setCurrentText(previous or now)
        finally:
            self._loading=False
        self._refresh_tables()

    def _refresh_tables(self):
        cycle=self._selected_month()
        if cycle is None:
            self.history_summary.setText(t("plan.bad_month"))
            self.closure_status.setText(t("plan.bad_month"))
            return
        self._load_profiles()
        self._load_expected(cycle)
        self._load_history(cycle)
        self._load_closing(cycle)

    def _load_profiles(self):
        self._profiles=self.history.profile()
        set_rows(self.profiles,[
            (r["nazwa"],r["dostawca"] or "—",r["kategoria"] or "—",
             t("plan.type."+r["typ"]) if r["typ"] else "—",
             r["cykl_od"] or "—",
             t("plan.active") if r["aktywny"] else t("plan.inactive"))
            for r in self._profiles
        ],[int(r["id"]) for r in self._profiles])

    def _load_expected(self, cycle):
        self._expectations=self.history.oczekiwania(cycle)
        set_rows(self.expected,[
            (r["nazwa"],r["oczekiwany_od"],
             t("plan.state."+r["state"]),
             ",".join(str(n) for n in r["invoice_ids"]) or "—",
             r["powod_wyjatku"] or "—")
            for r in self._expectations
        ],[int(r["id"]) for r in self._expectations])

    def _load_history(self, cycle):
        self._invoices=self.history.faktury(cycle)
        state=self.history.miesiac(cycle)
        self.history_summary.setText(t(
            "history.summary",
            billed=grosze_na_kwote(state["billed_grosze"]),
            paid=grosze_na_kwote(state["paid_service_grosze"]),
            paid_month=grosze_na_kwote(state["payments_in_month_grosze"]),
            unpaid=grosze_na_kwote(state["unpaid_grosze"]),
            count=state["invoice_count"],
            withdrawn=state["withdrawn_count"]
        ))
        set_rows(self.history_invoices,[
            (r["dostawca"],r["numer"] or "—",
             grosze_na_kwote(r["kwota_grosze"]),
             t("form.status_paid" if r["status"]=="oplacony" else "form.status_due"),
             r["termin_platnosci"] or "—",
             r["data_oplacenia"] or t("history.no_paid_date"),
             t("history.withdrawn") if r["wycofano_utc"] else t("history.active"))
            for r in self._invoices
        ],[int(r["id"]) for r in self._invoices])
        events=self.history.dziennik_miesiaca(cycle)
        set_rows(self.audit,[
            (r["utworzono_utc"],r["obiekt_typ"]+" #"+r["obiekt_id"],
             r["operacja"],r["powod"] or "—")
            for r in events
        ],[int(r["id"]) for r in events])

    def _load_closing(self, cycle):
        state=self.history.miesiac(cycle)
        if state["closed"]:
            label=t("closing.closed")
        elif state["documents_confirmed"]:
            label=t("closing.documents_only")
        else:
            label=t("closing.not_confirmed")
        self.closure_status.setText(t(
            "closing.summary",cycle=cycle,state=label,
            invoices=state["invoice_count"],
            unpaid=state["unpaid_count"],
            unpaid_amount=grosze_na_kwote(state["unpaid_grosze"]),
            expected=state["expected_count"],
            unresolved=state["unresolved_expected"],
        ))
        set_rows(self.close_expectations,[
            (r["nazwa"],r["oczekiwany_od"],t("plan.state."+r["state"]),
             ",".join(map(str,r["invoice_ids"])) or "—")
            for r in self._expectations
        ],[int(r["id"]) for r in self._expectations])
        self.confirm_btn.setEnabled(state["finished"] and not state["documents_confirmed"])
        self.empty_confirmation.setEnabled(not state["invoice_count"])

    def _profile(self):
        ident=chosen_id(self.profiles)
        return next((r for r in self._profiles if r["id"]==ident),None)

    def _expectation(self):
        ident=chosen_id(self.expected)
        return next((r for r in self._expectations if r["id"]==ident),None)

    def _invoice(self):
        ident=chosen_id(self.history_invoices)
        return next((r for r in self._invoices if r["id"]==ident),None)

    def _fail(self,error):
        QMessageBox.warning(self,t("plan.title"),str(error))

    def _mutated(self, invoice_id: int | None = None):
        self.refresh()
        self.daneZmienione.emit(invoice_id)

    def _create_profile(self):
        dlg=FormularzProfilu([dict(r) for r in self.rejestr.kategorie()],parent=self)
        if dlg.exec()!=QDialog.DialogCode.Accepted:
            return
        params=dlg.values()
        name=params["nazwa"]
        if any(r["nazwa"].casefold()==name.casefold() for r in self._profiles):
            self._fail(t("plan.duplicate"))
            return
        if not confirm(self,t("plan.title"),t("plan.profile.confirm",name=name)):
            return
        try:
            self.plan.utworz_profil(**params)
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated()

    def _edit_schedule(self):
        profile=self._profile()
        if profile is None or not profile["aktywny"]:
            self._fail(t("plan.choose_active"))
            return
        dlg=FormularzProfilu(
            [dict(r) for r in self.rejestr.kategorie()],profile,self
        )
        if dlg.exec()!=QDialog.DialogCode.Accepted:
            return
        params=dlg.values()
        if not confirm(self,t("plan.title"),
                       t("plan.schedule.confirm",cycle=params["cykl_od"])):
            return
        try:
            self.plan.zmien_harmonogram(
                int(profile["id"]),
                cykl_od=params["cykl_od"],typ=params["typ"],
                co_ile_miesiecy=params["co_ile_miesiecy"],
                cykl_kotwicy=params["cykl_kotwicy"],
                przesuniecie_dni=params["przesuniecie_dni"],
            )
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated()

    def _toggle_profile(self):
        profile=self._profile()
        if profile is None:
            self._fail(t("plan.choose_profile"))
            return
        active=not bool(profile["aktywny"])
        reason,ok=QInputDialog.getText(
            self,t("plan.title"),t("plan.reason")
        )
        if not ok or not reason.strip():
            return
        if not confirm(self,t("plan.title"),
                       t("plan.toggle.confirm",name=profile["nazwa"])):
            return
        try:
            self.plan.ustaw_aktywnosc(
                int(profile["id"]),active,powod=reason
            )
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated()

    def _generate(self):
        cycle=self._selected_month()
        if cycle is None:
            self._fail(t("plan.bad_month"))
            return
        if not confirm(self,t("plan.title"),t("plan.generate.confirm",cycle=cycle)):
            return
        try:
            self.plan.generuj_oczekiwania(cycle)
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated()

    def _set_exception(self):
        expected=self._expectation()
        if expected is None:
            self._fail(t("plan.choose_expected"))
            return
        options=[(t("plan.state.not_issued"),"nie_wystawiono"),
                 (t("plan.state.uncertain"),"niepewne")]
        label,ok=QInputDialog.getItem(
            self,t("plan.exception"),t("plan.exception.type"),
            [x[0] for x in options],0,False
        )
        if not ok:
            return
        kind=dict(options)[label]
        reason,ok=QInputDialog.getMultiLineText(
            self,t("plan.exception"),t("plan.reason")
        )
        if not ok or not reason.strip():
            return
        if not confirm(self,t("plan.exception"),
                       t("plan.exception.confirm",name=expected["nazwa"])):
            return
        try:
            self.plan.oznacz_wyjatek(int(expected["id"]),typ=kind,powod=reason)
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated()

    def _clear_exception(self):
        expected=self._expectation()
        if expected is None or not expected["wyjatek"]:
            self._fail(t("plan.choose_exception"))
            return
        reason,ok=QInputDialog.getText(self,t("plan.title"),t("plan.reason"))
        if not ok or not reason.strip():
            return
        if not confirm(self,t("plan.title"),t("plan.exception.clear_confirm")):
            return
        try:
            self.plan.anuluj_wyjatek(int(expected["id"]),powod=reason)
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated()

    def _link(self):
        expected=self._expectation()
        if expected is None:
            self._fail(t("plan.choose_expected"))
            return
        candidates=[
            r for r in self._invoices if r["wycofano_utc"] is None
            and r["id"] not in expected["invoice_ids"]
        ]
        if not candidates:
            self._fail(t("plan.no_link_candidates"))
            return
        options={
            f"#{r['id']} — {r['dostawca']} / {r['numer']} "
            f"({grosze_na_kwote(r['kwota_grosze'])} zł)":int(r["id"])
            for r in candidates
        }
        picked,ok=QInputDialog.getItem(
            self,t("plan.link"),t("plan.link.choose"),list(options),0,False
        )
        if not ok:
            return
        if not confirm(self,t("plan.link"),t("plan.link.confirm")):
            return
        try:
            self.plan.powiaz(int(expected["id"]),options[picked])
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated()

    def _unlink(self):
        expected=self._expectation()
        if expected is None or not expected["invoice_ids"]:
            self._fail(t("plan.no_links"))
            return
        options={str(x):x for x in expected["invoice_ids"]}
        picked,ok=QInputDialog.getItem(
            self,t("plan.unlink"),t("plan.unlink.choose"),list(options),0,False
        )
        if not ok or not confirm(self,t("plan.unlink"),t("plan.unlink.confirm")):
            return
        try:
            self.plan.odlacz(int(expected["id"]),options[picked])
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated()

    def _paid(self):
        invoice=self._invoice()
        if invoice is None or invoice["wycofano_utc"]:
            self._fail(t("history.choose_active"))
            return
        date_dialog=QDialog(self)
        date_dialog.setWindowTitle(t("history.mark_paid"))
        layout=QVBoxLayout(date_dialog)
        layout.addWidget(QLabel(t("history.choose_payment_date")))
        chosen=QDateEdit()
        chosen.setCalendarPopup(True)
        chosen.setDisplayFormat("yyyy-MM-dd")
        from PySide6.QtCore import QDate
        chosen.setDate(
            QDate.fromString(invoice["data_oplacenia"],"yyyy-MM-dd")
            if invoice["data_oplacenia"] else QDate.currentDate()
        )
        chosen.setObjectName("historyPaymentDate")
        layout.addWidget(chosen)
        buttons=QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(date_dialog.accept)
        buttons.rejected.connect(date_dialog.reject)
        layout.addWidget(buttons)
        if date_dialog.exec()!=QDialog.DialogCode.Accepted:
            return
        paid_date=chosen.date().toString("yyyy-MM-dd")
        if not confirm(self,t("history.mark_paid"),
                       t("history.mark_paid.confirm",date=paid_date)):
            return
        try:
            self.finanse.ustaw_oplacona(
                int(invoice["id"]),paid_date,
                expected_version=int(invoice["wersja_rekordu"]),
            )
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated(int(invoice["id"]))

    def _reason_action(self, *, method: str):
        invoice=self._invoice()
        if invoice is None:
            self._fail(t("history.choose_invoice"))
            return
        requirements={
            "revoke": invoice["status"]=="oplacony" and not invoice["wycofano_utc"],
            "withdraw": not invoice["wycofano_utc"],
            "restore": bool(invoice["wycofano_utc"]),
        }
        if not requirements[method]:
            self._fail(t("history.invalid_action"))
            return
        title=t("history."+method)
        reason,ok=QInputDialog.getMultiLineText(self,title,t("plan.reason"))
        if not ok or not reason.strip():
            return
        if not confirm(self,title,t("history.reason.confirm",reason=reason)):
            return
        try:
            version=int(invoice["wersja_rekordu"])
            if method=="revoke":
                self.finanse.cofnij_oplacenie(
                    int(invoice["id"]),powod=reason,expected_version=version
                )
            elif method=="withdraw":
                self.finanse.wycofaj(
                    int(invoice["id"]),powod=reason,expected_version=version
                )
            else:
                self.finanse.przywroc(
                    int(invoice["id"]),powod=reason,expected_version=version
                )
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        self._mutated(int(invoice["id"]))

    def _revoke_payment(self):
        self._reason_action(method="revoke")

    def _withdraw(self):
        self._reason_action(method="withdraw")

    def _restore(self):
        self._reason_action(method="restore")

    def _confirm_month(self):
        cycle=self._selected_month()
        if cycle is None:
            self._fail(t("plan.bad_month"))
            return
        # Generujemy na żądanie, a przed potwierdzeniem pokazujemy listę:
        # user musi zobaczyć wszystkie oczekiwane dokumenty.
        try:
            created=self.plan.generuj_oczekiwania(cycle)
            if created:
                self.refresh()
                QMessageBox.information(
                    self,t("closing.confirm"),
                    t("closing.generated",count=len(created)),
                )
                return
            current=self.history.miesiac(cycle)
            if not current["finished"]:
                raise ValueError(t("closing.too_early"))
            if current["unresolved_expected"]:
                raise ValueError(t("closing.resolve_first"))
            if not current["invoice_count"] and not self.empty_confirmation.isChecked():
                raise ValueError(t("closing.empty_required"))
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            return
        if not confirm(self,t("closing.confirm"),t(
            "closing.confirm.question",cycle=cycle,
            count=current["invoice_count"],
            unpaid=current["unpaid_count"],
        )):
            return
        try:
            self.finanse.potwierdz_kompletnosc(
                cycle,brak_rachunkow=self.empty_confirmation.isChecked(),
                dzisiaj=now_pl().date().isoformat(),
            )
        except (ValueError,sqlite3.Error) as error:
            self._fail(error)
            self.refresh()
            return
        self.empty_confirmation.setChecked(False)
        self._mutated()
