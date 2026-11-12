# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Tylko fikcyjny, syntetyczny QR; bez prywatnych faktur użytkownika."""
from __future__ import annotations

import base64
import tempfile
import threading
import unittest
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter, QPdfWriter

from uslugi.kody_qr import OdczytQRAnulowany, odczytaj_kody_qr, rozpoznaj_platnosc

SYNTHETIC = "1234563218|PL|07109010140000000000000001|001234|Operator Testowy|FV/DEMO/11/2026|||"
QR_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAALQAAAC0AQAAAAAVtjufAAABhUlEQVR42u2XsY0dQQxDn4zL33Sw/Ze1HXAqoIN/BhxcKMCJlSxGATEjkZR2yk9xf/Fz/M+v52fmXOBymDkzc1bxbTkcuPfS2C6/aw4ZBn2cw5z9ugmee/OS3fp/fT7je5Cz3t8voJxecHwdKIv9nTLg39IFs6Zf+h1iQvM5ZRFfNUCD0Zpd/GrSpoG0UFfxSQxpUCp1Ef8LhBe9dMLJnTx7/KGNRTQULe3u/Z9Mv5UVDlyzev9WWm6/v58wgOp3PwrO/PL+MN5PKe21X+A5pv/y9Z7e/8/7/+p/nf5ChdmVCSSvIAAAAASUVORK5CYII="


class TestQR(unittest.TestCase):
    def test_rozpoznanie_znanego_formatu(self):
        result = rozpoznaj_platnosc(SYNTHETIC)
        self.assertIsNotNone(result)
        self.assertEqual(result.kwota_grosze, 1234)
        self.assertEqual(result.numer_konta, "07109010140000000000000001")
        self.assertEqual(result.odbiorca, "Operator Testowy")

    def test_nieznane_i_nieprawidlowe_qr_nie_wymuszaja_danych(self):
        self.assertIsNone(rozpoznaj_platnosc("https://example.invalid/pay"))
        self.assertIsNone(rozpoznaj_platnosc(SYNTHETIC.replace(
            "07109010140000000000000001", "00109010140000000000000001"
        )))
        self.assertIsNone(rozpoznaj_platnosc(SYNTHETIC.replace("001234", "12,34")))

    def test_odczyt_z_fikcyjnego_pdf(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "faktura-testowa.pdf"
            writer = QPdfWriter(str(path))
            writer.setResolution(72)
            painter = QPainter(writer)
            self.assertTrue(painter.isActive())
            bitmap = QImage.fromData(base64.b64decode(QR_PNG_BASE64), "PNG")
            self.assertFalse(bitmap.isNull())
            painter.drawImage(QRect(120, 210, 310, 310), bitmap)
            painter.end()
            result = odczytaj_kody_qr(path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].strona, 0)
            self.assertEqual(result[0].tresc, SYNTHETIC)
            self.assertEqual(result[0].platnosc.kwota_grosze, 1234)

    def test_anulowanie(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pusty.pdf"
            path.write_bytes(b"%PDF-1.4\n%%EOF\n")
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(OdczytQRAnulowany):
                odczytaj_kody_qr(path, przerwij=cancel)


if __name__ == "__main__":
    unittest.main()
