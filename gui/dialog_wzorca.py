# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Jawny przegląd JSON i osobna zgoda na zapis / aktualizację wzorca."""
from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
)

from i18n import t
from uslugi.wzorce import zatwierdz_strukture


def zaakceptuj_wzorzec(parent, proposed: dict, *, aktualizacja: bool = False) -> dict | None:
    """Nie zapisuje pliku. Zwraca JSON wyłącznie po kliknięciu akceptacji."""
    box = QDialog(parent)
    box.setWindowTitle(t("patterns.dialog.update" if aktualizacja else "patterns.dialog.new"))
    box.resize(820, 620)
    layout = QVBoxLayout(box)
    opis = QLabel(t("patterns.dialog.help"))
    opis.setWordWrap(True)
    layout.addWidget(opis)
    editor = QPlainTextEdit()
    editor.setObjectName("edytorWzorcaJSON")
    editor.setPlainText(json.dumps(proposed, ensure_ascii=False, indent=2, sort_keys=True))
    layout.addWidget(editor)
    actions = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )
    actions.button(QDialogButtonBox.StandardButton.Save).setText(t("patterns.dialog.approve"))
    actions.button(QDialogButtonBox.StandardButton.Cancel).setText(t("settings.cancel"))
    actions.accepted.connect(box.accept)
    actions.rejected.connect(box.reject)
    layout.addWidget(actions)
    if box.exec() != QDialog.DialogCode.Accepted:
        return None
    # Waliduj po zamknięciu okna, zapis wykonywany jest tylko w GUI przez usługę.
    return zatwierdz_strukture(json.loads(editor.toPlainText()))
