# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Panel Agenta: odczyt wyników i bezpieczny dziennik, zero operacji finansowych."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ai_core.hybrid import MonitorReport
from i18n import t
from uslugi.rachunki import grosze_na_kwote


def model_details(report: MonitorReport) -> list[str]:
    lines = []
    if report.model_id:
        lines.append(t("agent.model.selected", model=report.model_id))
    if report.model_reason:
        lines.append(t("agent.reason." + report.model_reason))
    return lines


def report_text(report: MonitorReport | None) -> str:
    if report is None:
        return t("agent.no_results")
    data = report.summary
    lines = [
        t("agent.scope." + report.mode),
        t("agent.date", date=report.reference_date),
        t("agent.invoices", count=data["invoices"]),
        t("agent.unpaid", amount=grosze_na_kwote(data["unpaid_grosze"])),
        t("agent.overdue", count=data["overdue"]),
        t("agent.due_soon", count=data["due_soon"]),
        t("agent.paid_without_date", count=data["paid_without_date"]),
        t("agent.missing", count=data["missing_expected"]),
        t("agent.model." + report.model_status),
        *model_details(report),
    ]
    if report.findings:
        lines.append("")
        lines.append(t("agent.findings"))
        for item in report.findings[:20]:
            confirmation = t("agent.verified") if item["verification"] == "verified" else t("agent.unverified")
            lines.append(f"- [{confirmation}] {item['summary']}")
    if report.proposals:
        lines.append("")
        lines.append(t("agent.proposals"))
        for item in report.proposals[:20]:
            lines.append(
                f"- {item['kind']} (ID: {item['target_id']}): {item['reason']}"
            )
        lines.append(t("agent.no_auto_actions"))
    if report.uncertainties:
        lines.append("")
        lines.append(t("agent.uncertainties"))
        for value in report.uncertainties[:20]:
            lines.append("- " + value)
    if report.specialists:
        lines.append("")
        lines.append(t("agent.specialists.title"))
        for item in report.specialists:
            role = item["role"]
            lines.append(
                "- " + t("agent.specialists." + role) + " — " + item["model_id"]
                + ": " + t("agent.specialists." + item["status"])
            )
            if item["status"] == "ready":
                for finding in item["findings"]:
                    certainty = (
                        t("agent.verified") if finding["verification"] == "verified"
                        else t("agent.unverified")
                    )
                    lines.append("  • [" + certainty + "] " + finding["summary"])
                for uncertainty in item["uncertainties"]:
                    lines.append("  • " + uncertainty)
        lines.append(t("agent.specialists.no_authority"))
    return "\n".join(lines)


class PanelAgenta(QDialog):
    manualRequested = Signal()
    cancelRequested = Signal()
    otworz_fakture = Signal(int, str)

    def __init__(self, parent=None, *, embedded=False):
        super().__init__(parent)
        self._embedded = embedded
        self.setObjectName("panelAgenta")
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        else:
            self.setMinimumSize(650, 540)
            self.resize(800, 650)
        layout = QVBoxLayout(self)
        if embedded:
            self.heading = QLabel()
            self.heading.setObjectName("pulpitTytul")
            layout.addWidget(self.heading)
        else:
            self.heading = None
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)
        self.wyniki = QPlainTextEdit()
        self.wyniki.setReadOnly(True)
        self.wyniki.setObjectName("wynikiMonitora")
        layout.addWidget(self.wyniki, 3)
        self.log_label = QLabel()
        layout.addWidget(self.log_label)
        self.dziennik = QPlainTextEdit()
        self.dziennik.setReadOnly(True)
        self.dziennik.setObjectName("dziennikAgenta")
        layout.addWidget(self.dziennik, 2)
        buttons = QHBoxLayout()
        self.manual = QPushButton()
        self.manual.clicked.connect(self.manualRequested.emit)
        self.manual.setObjectName("analizaPelnaAgenta")
        buttons.addWidget(self.manual)
        self.cancel = QPushButton()
        self.cancel.clicked.connect(self.cancelRequested.emit)
        buttons.addWidget(self.cancel)
        self.copy = QPushButton()
        self.copy.clicked.connect(self._copy_log)
        buttons.addWidget(self.copy)
        self.save = QPushButton()
        self.save.clicked.connect(self._save_log)
        buttons.addWidget(self.save)
        layout.addLayout(buttons)
        self.faktura = QPushButton()
        self.faktura.hide()
        self.faktura.clicked.connect(self._pokaz_fakture)
        layout.addWidget(self.faktura, 0, Qt.AlignmentFlag.AlignLeft)
        self.report: MonitorReport | None = None
        self.logs = ""
        self.przetlumacz()

    def przetlumacz(self) -> None:
        self.setWindowTitle(t("agent.title"))
        if self.heading is not None:
            self.heading.setText(t("nav.agent"))
        self.info.setText(t("agent.warning"))
        self.summary_label.setText(t("agent.results"))
        self.log_label.setText(t("agent.log"))
        self.manual.setText(t("agent.manual"))
        self.cancel.setText(t("agent.cancel"))
        self.copy.setText(t("agent.copy"))
        self.save.setText(t("agent.save"))
        self.faktura.setText(t("agent.open_reviewed_invoice"))
        self.wyniki.setPlainText(report_text(self.report))

    def update_content(self, report: MonitorReport | None, logs: str, working: bool) -> None:
        self.report = report
        self.logs = logs
        self.wyniki.setPlainText(report_text(report))
        self.dziennik.setPlainText(logs)
        self.cancel.setEnabled(working)
        self.manual.setEnabled(True)
        self.faktura.setVisible(report is not None and report.invoice_id is not None)

    def _pokaz_fakture(self):
        if self.report is not None and self.report.invoice_id is not None:
            self.otworz_fakture.emit(self.report.invoice_id, self.report.data_revision)

    def reject(self) -> None:
        if not self._embedded:
            super().reject()

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self.logs)

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, t("agent.save"), str(Path.home() / "swistak-agent-log.txt"),
            "Text (*.txt)",
        )
        if path:
            Path(path).write_text(self.logs, encoding="utf-8")
