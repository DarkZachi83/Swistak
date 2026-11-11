# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Integracja W1–W4 — wyłącznie syntetyczna faktura internetowa.

Zakaz wykorzystywania dokumentów i danych finansowych użytkownika w CI.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

import ustawienia
from gui.okno_glowne import OknoGlowne
from uslugi.analiza_llm import POLA, analizuj_lokalnie
from uslugi.dopasowanie_wzorca import zaproponuj_wzorzec
from uslugi.propozycja_wzorca import zaproponuj_aktualizacje
from uslugi.rachunki import RejestrRachunkow
from uslugi.wzorce import MagazynWzorcow, wskazowki_dla_modelu


TEKST = (
    "Faktura nr DEMO/FV/2026\n"
    "Sprzedawca:\nOperator Sieci DEMO\nNIP: 123-456-32-18\n"
    "Nabywca:\nNabywca WYŁĄCZNIE TESTOWY\nNIP 123-456-32-24\n"
    "Data wystawienia: 10.11.2026\n"
    "Termin płatności: 25.11.2026\n"
    "Wartość faktury: 42,00 PLN\n"
    "Usługa internetowa — przykład niepowiązany z użytkownikiem\n"
)


class TestWzorzecGemma(unittest.TestCase):
    def test_wylacznie_zatwierdzone_reguly_do_lokalnego_llm(self):
        template = zaproponuj_wzorzec(
            TEKST, "Operator Sieci DEMO", "Internet",
            {"termin_platnosci": "Termin znajduje się w górnej części."},
            "Nie myl numeru klienta z numerem faktury.",
        )
        self.assertNotIn("42,00", wskazowki_dla_modelu(template))
        self.assertNotIn("Nabywca WYŁĄCZNIE TESTOWY", wskazowki_dla_modelu(template))
        mocked_result = {
            "message": {"content": json.dumps(
                {p: {"wartosc": None, "dowod": None} for p in POLA}
            )}
        }
        handler = MagicMock()
        handler.open.return_value.__enter__.return_value = io.BytesIO(
            json.dumps(mocked_result).encode("utf-8")
        )
        with patch("uslugi.analiza_llm.build_opener", return_value=handler):
            analizuj_lokalnie(TEKST, ["Internet", "Inne"],
                            model="model-test:1", wzorzec=template)
        request = handler.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        body = json.loads(request.data)
        system = body["messages"][0]["content"]
        source = body["messages"][1]["content"]
        self.assertIn("WZORZEC_JSON", system)
        self.assertIn("Termin znajduje się", system)
        self.assertIn("Nie myl numeru klienta", system)
        self.assertNotIn("42,00", system)
        self.assertNotIn("Nabywca WYŁĄCZNIE TESTOWY", system)
        self.assertIn("42,00", source)  # wartość tylko w aktualnym OCR
        self.assertFalse(body["stream"])

    def test_nieaktywny_wzorzec_nie_trafia_do_llm(self):
        template = zaproponuj_wzorzec(TEKST, "Operator Sieci DEMO", "Internet")
        template["status"] = "inactive"
        with self.assertRaises(ValueError):
            wskazowki_dla_modelu(template)

    def test_aktualizacja_nie_kopiuje_wartosci_z_faktury(self):
        prev = zaproponuj_wzorzec(
            TEKST, "Operator Sieci DEMO", "Internet", {},
            "Szukaj daty w pierwszym nagłówku.",
        )
        next_version = zaproponuj_wzorzec(
            TEKST, "Operator Sieci DEMO", "Internet",
            {"kwota_do_zaplaty": "Odczytaj kwotę z podsumowania."},
            "Nie myl salda z kwotą do zapłaty.",
        )
        result = zaproponuj_aktualizacje(prev, next_version)
        self.assertIn("Szukaj daty", result["agent_notes"][0])
        self.assertIn("Nie myl salda", result["agent_notes"][1])
        self.assertEqual(result["revision"], 1)
        self.assertIn("Odczytaj kwotę", result["fields"]["kwota_do_zaplaty"]["note"])
        self.assertNotIn("42,00", json.dumps(result, ensure_ascii=False))


class TestInterfejsWzorcow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _pdf(path: Path):
        writer = QPdfWriter(str(path))
        painter = QPainter(writer)
        if not painter.isActive():
            raise RuntimeError("Nie można utworzyć syntetycznego dokumentu")
        painter.drawText(100, 100, "Syntetyczna faktura TESTOWA")
        painter.end()

    def test_po_zapisie_propozycja_wymaga_osobnej_zgody_i_chroni_historie(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pdf = root / "syntetyczna.pdf"
            self._pdf(pdf)
            db = RejestrRachunkow(root / "prywatny-katalog-testowy")
            kat_id = db.dodaj_kategorie("Internet")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "ustawienia.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "model-test:1"})
                    win = OknoGlowne(db)
                    win.show()
                    self.app.processEvents()
                    win.otworz_pdf(pdf)
                    doc_id = win.aktualny_dokument_id
                    win.pole_odczytu.setPlainText(TEKST)
                    win._wykryj_wzorzec(TEKST)
                    self.assertIsNone(win._aktywny_wzorzec)
                    win.ed_dostawca.setText("Operator Sieci DEMO")
                    win.ed_kwota.setText("42,00")
                    win.wybor_kategoria.setCurrentIndex(
                        win.wybor_kategoria.findData(kat_id)
                    )
                    win._komentarze_wzorca["termin_platnosci"] = (
                        "Termin znajduje się w górnej części."
                    )
                    win.notatki_wzorca.setPlainText(
                        "Nie myl numeru klienta z numerem faktury."
                    )
                    win.karty.setCurrentIndex(win.ETAP_FAKTURA)
                    win.zapisz_przycisk.click()
                    self.assertEqual(db.rachunek(doc_id)["kwota_grosze"], 4200)
                    self.assertFalse(win.btn_proponuj_wzorzec.isHidden())
                    store = MagazynWzorcow(db.katalog)
                    self.assertEqual(store.lista(), [])  # zapis faktury ≠ zapis wzorca

                    with patch("gui.okno_glowne.zaakceptuj_wzorzec",
                               return_value=None):
                        win._zaproponuj_zapis_wzorca()
                    self.assertEqual(store.lista(), [])  # anulowanie dialogu

                    with patch("gui.okno_glowne.zaakceptuj_wzorzec",
                               side_effect=lambda parent, candidate, **kw: candidate):
                        win._zaproponuj_zapis_wzorca()
                    templates = store.lista()
                    self.assertEqual(len(templates), 1)
                    item = templates[0]
                    self.assertEqual(item["revision"], 1)
                    self.assertEqual(item["category"], "Internet")
                    self.assertEqual(item["identification"]["seller_nip"],
                                     "1234563218")
                    self.assertIn("Termin znajduje się",
                                  item["fields"]["termin_platnosci"]["note"])
                    self.assertNotIn("42,00", json.dumps(item))
                    self.assertNotIn("Nabywca WYŁĄCZNIE TESTOWY", json.dumps(item))

                    win.notatki_wzorca.setPlainText(
                        "Zachowaj daty w formacie RRRR-MM-DD."
                    )
                    with patch("gui.okno_glowne.zaakceptuj_wzorzec",
                               side_effect=lambda parent, candidate, **kw: candidate):
                        win._zaproponuj_zapis_wzorca()
                    updated = store.pobierz(item["template_id"])
                    self.assertEqual(updated["revision"], 2)
                    self.assertEqual(len(updated["agent_notes"]), 2)
                    self.assertTrue((store.katalog / "historia" /
                        f"{item['template_id']}.rev-000001.json").is_file())
                    self.assertEqual(db.rachunek(doc_id)["kwota_grosze"], 4200)
                    # Po kolejnym OCR dopasuje zatwierdzony wzorzec.
                    win._wykryj_wzorzec(TEKST)
                    self.assertEqual(win._dopasowanie_wzorca.poziom, "automatic")
                    self.assertEqual(win._aktywny_wzorzec["revision"], 2)
                    with patch("gui.okno_glowne.QThreadPool.globalInstance") as pool:
                        win._start_analizy()
                        pool.return_value.start.assert_called_once()
                        job = pool.return_value.start.call_args.args[0]
                        self.assertEqual(job.wzorzec["template_id"],
                                         updated["template_id"])
                    win.close()
            finally:
                db.zamknij()


if __name__ == "__main__":
    unittest.main()
