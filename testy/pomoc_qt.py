# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Sprzątanie okien testowych zgodnie z kolejnością zamykania aplikacji."""
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QWidget


def zamknij_widget(widget: QWidget) -> None:
    """Usuń obiekty Qt w wątku GUI, zanim Python zwolni ich opakowania."""
    widget.close()
    QThreadPool.globalInstance().waitForDone()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
