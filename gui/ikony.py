# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Ikony nawigacji rysowane w kolorze ciemnego motywu Świstaka."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from gui.motyw import TEKST


# Kontury w układzie współrzędnych 24 × 24. Kolejne pary tworzą linię łamaną.
LINIE = {
    "dashboard": (((3, 10), (12, 3), (21, 10)),
                  ((6, 9), (6, 21), (10, 21), (10, 15), (14, 15), (14, 21), (18, 21), (18, 9))),
    "new_invoice": (((5, 3), (14, 3), (19, 8), (19, 21), (5, 21), (5, 3)),
                    ((14, 3), (14, 8), (19, 8)), ((9, 14), (15, 14)), ((12, 11), (12, 17))),
    "invoices": (((3, 6), (9, 6), (11, 8), (21, 8), (21, 20), (3, 20), (3, 6)),
                 ((3, 11), (21, 11))),
    "statistics": (((3, 4), (3, 20), (21, 20)), ((8, 16), (8, 12)),
                   ((13, 16), (13, 7)), ((18, 16), (18, 4))),
    "plan": (((4, 6), (20, 6), (20, 21), (4, 21), (4, 6)), ((4, 10), (20, 10)),
             ((8, 3), (8, 7)), ((16, 3), (16, 7)), ((8, 15), (10, 17), (15, 13))),
    "history": (((12, 7), (12, 12), (16, 14)),),
    "agent": (((5, 8), (19, 8), (19, 19), (5, 19), (5, 8)), ((12, 8), (12, 4)),
              ((2, 12), (2, 15)), ((22, 12), (22, 15)), ((9, 16), (15, 16))),
    "settings": (((4, 6), (8, 6)), ((12, 6), (20, 6)), ((4, 12), (13, 12)),
                 ((17, 12), (20, 12)), ((4, 18), (7, 18)), ((11, 18), (20, 18))),
    "about": (((12, 11), (12, 17)),),
}
OKREGI = {
    "history": ((12, 12, 9),),
    "agent": ((9, 12, 0.5), (15, 12, 0.5)),
    "settings": ((10, 6, 2), (15, 12, 2), (9, 18, 2)),
    "about": ((12, 12, 9), (12, 7, 0.5)),
}


def ikona_nawigacji(klucz: str, rozmiar: int) -> QIcon:
    ikona = QIcon()
    for skala in (1, 2, 3):
        mapa = QPixmap(rozmiar * skala, rozmiar * skala)
        mapa.setDevicePixelRatio(skala)
        mapa.fill(Qt.GlobalColor.transparent)
        malarz = QPainter(mapa)
        try:
            malarz.setRenderHint(QPainter.RenderHint.Antialiasing)
            malarz.scale(rozmiar / 24, rozmiar / 24)
            pioro = QPen(QColor(TEKST), 2.2)
            pioro.setCapStyle(Qt.PenCapStyle.RoundCap)
            pioro.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            malarz.setPen(pioro)
            for linia in LINIE[klucz]:
                malarz.drawPolyline(QPolygonF([QPointF(x, y) for x, y in linia]))
            for x, y, r in OKREGI.get(klucz, ()):
                malarz.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
        finally:
            malarz.end()
        for tryb in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
            ikona.addPixmap(mapa, tryb)
    return ikona
