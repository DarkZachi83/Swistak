# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Panel Agenta: odczyt wyników i bezpieczny dziennik, zero operacji finansowych."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ai_core.hybrid import MonitorReport
from i18n import t
from uslugi.rachunki import grosze_na_kwote


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
    return "\n".join(lines)


class PanelAgenta(QDialog):
    manualRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panelAgenta")
        self.setMinimumSize(650, 540)
        self.resize(800, 650)
        layout = QVBoxLayout(self)
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
        self.report: MonitorReport | None = None
        self.logs = ""
        self.przetlumacz()

    def przetlumacz(self) -> None:
        self.setWindowTitle(t("agent.title"))
        self.info.setText(t("agent.warning"))
        self.summary_label.setText(t("agent.results"))
        self.log_label.setText(t("agent.log"))
        self.manual.setText(t("agent.manual"))
        self.cancel.setText(t("agent.cancel"))
        self.copy.setText(t("agent.copy"))
        self.save.setText(t("agent.save"))
        self.wyniki.setPlainText(report_text(self.report))

    def update_content(self, report: MonitorReport | None, logs: str, working: bool) -> None:
        self.report = report
        self.logs = logs
        self.wyniki.setPlainText(report_text(report))
        self.dziennik.setPlainText(logs)
        self.cancel.setEnabled(working)
        self.manual.setEnabled(True)

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self.logs)

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, t("agent.save"), str(Path.home() / "swistak-agent-log.txt"),
            "Text (*.txt)",
        )
        if path:
            Path(path).write_text(self.logs, encoding="utf-8")
