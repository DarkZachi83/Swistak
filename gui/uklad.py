# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Układ elementów, który zawija je przy ograniczonej szerokości."""
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget


class Siatka(QWidget):
    def __init__(self, kolumny: int, *, szerokosc: int = 0):
        super().__init__()
        self._kolumny = kolumny
        self._szerokosc = szerokosc
        self._ostatni_uklad = None
        self._elementy = []
        self._siatka = QGridLayout(self)
        self._siatka.setContentsMargins(0, 0, 0, 0)
        # Liczbę kolumn wyznacza dostępna szerokość rodzica.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def dodaj(self, widget: QWidget) -> None:
        self._elementy.append(widget)
        widget.setParent(self)
        self._ostatni_uklad = None
        self.dopasuj()

    def minimumSizeHint(self):
        rozmiar = super().minimumSizeHint()
        rozmiar.setWidth(max(
            (self._minimum(w) for w in self._elementy), default=0
        ))
        return rozmiar

    @staticmethod
    def _minimum(widget: QWidget) -> int:
        return max(widget.minimumWidth(), widget.minimumSizeHint().width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.dopasuj()

    def changeEvent(self, event):
        super().changeEvent(event)
        self.dopasuj()

    def dopasuj(self):
        szerokosc = max(self._szerokosc, *(self._minimum(w) for w in self._elementy), 1)
        odstep = max(0, self._siatka.horizontalSpacing())
        liczba = max(1, min(self._kolumny, (self.width() + odstep) // (szerokosc + odstep)))
        if liczba == self._ostatni_uklad:
            return
        self._ostatni_uklad = liczba
        for i, widget in enumerate(self._elementy):
            self._siatka.removeWidget(widget)
            self._siatka.addWidget(widget, i // liczba, i % liczba)
        for i in range(self._kolumny):
            self._siatka.setColumnStretch(i, int(i < liczba))
