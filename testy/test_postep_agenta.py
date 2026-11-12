# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Postęp lokalnej analizy AI: testy na fikcyjnych danych, bez Ollamy i faktur."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

import ustawienia
from gui.analiza_worker import ZadanieAnalizy
from gui.okno_glowne import OknoGlowne
from i18n import set_language
from uslugi.analiza_llm import POLA, analizuj_lokalnie
from uslugi.rachunki import RejestrRachunkow


class TestPostepAgenta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_language("pl")

    def test_pasek_nie_pokazuje_fikcyjnych_procentow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "prefs.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    win.show()
                    self.app.processEvents()
                    # Pasek jest na wewnętrznej karcie DANE, a start aplikacji
                    # pokazuje Odczyt PDF: najpierw odsłoń panel analizy.
                    win.karty.setCurrentIndex(win.ETAP_ANALIZA)
                    win.zakladki_ai.setCurrentIndex(0)
                    self.app.processEvents()
                    try:
                        self.assertFalse(win.postep_ai.isVisible())
                        self.assertEqual(win.postep_ai.objectName(), "postepPracyAgenta")
                        self.assertTrue(win.karta_ai_dane.isAncestorOf(win.postep_ai))
                        win._start_postep_ai()
                        self.assertTrue(win.postep_ai.isVisible())
                        self.assertEqual(win.postep_ai.minimum(), 0)
                        self.assertEqual(win.postep_ai.maximum(), 0)

                        # Etap raportowany z wątku dla odpowiedniego dokumentu.
                        job = ZadanieAnalizy(10, "Fikcyjny tekst", ["Inne"], "gemma3:4b")
                        win.aktualny_dokument_id = 10
                        win._zadanie_ai = job
                        win._etap_postepu_ai(9, "ollama")
                        self.assertNotIn("Ollama (", win.info_ai.text())
                        win._etap_postepu_ai(10, "ollama")
                        self.assertIn("gemma3:4b", win.info_ai.text())
                        win._etap_postepu_ai(10, "validate")
                        self.assertIn("Sprawdzanie odpowiedzi", win.info_ai.text())

                        # Anulowanie nie pozwala na pozorne przejście do kolejnego etapu.
                        job.przerwij.set()
                        state = win.info_ai.text()
                        win._etap_postepu_ai(10, "ollama")
                        self.assertEqual(win.info_ai.text(), state)

                        win._analiza_anulowana(10)
                        self.assertFalse(win.postep_ai.isVisible())
                        self.assertEqual(win.postep_ai.maximum(), 100)
                        self.assertEqual(win.postep_ai.value(), 0)

                        win._start_postep_ai()
                        win._koniec_postepu_ai(True)
                        self.assertTrue(win.postep_ai.isVisible())
                        self.assertEqual(win.postep_ai.value(), 100)
                        self.assertEqual(win.postep_ai.maximum(), 100)

                        win._wyczysc_analize()
                        self.assertFalse(win.postep_ai.isVisible())
                        self.assertEqual(win.postep_ai.value(), 0)
                        win.change_language("en")
                        self.assertEqual(win.postep_ai.accessibleName(),
                                         "AI agent progress")
                    finally:
                        win.close()
            finally:
                db.zamknij()

    def test_transport_raportuje_istniejace_etapy(self):
        fake_fields = {name: {"wartosc": None, "dowod": None} for name in POLA}
        response = {"message": {"content": json.dumps(fake_fields)}}
        handler = MagicMock()
        handler.open.return_value.__enter__.return_value = io.BytesIO(
            json.dumps(response).encode("utf-8")
        )
        stages = []
        with patch("uslugi.analiza_llm.build_opener", return_value=handler):
            result = analizuj_lokalnie(
                "FAKTURA FIKCYJNA. Kwota nieznana.",
                ["Inne"], postep=stages.append,
            )
        self.assertEqual(stages, ["ollama", "validate"])
        self.assertEqual(result.model, "gemma3:4b")

    def test_worker_przekazuje_etapy_i_wynik_bez_danych_prywatnych(self):
        sentinel = object()
        events = []
        done = []
        job = ZadanieAnalizy(7, "FIKCYJNE", ["Inne"], "demo:1")
        job.sygnaly.etap.connect(lambda doc, step: events.append((doc, step)))
        job.sygnaly.gotowe.connect(lambda doc, result: done.append((doc, result)))

        def fake_llm(text, categories, model, *, wzorzec, postep):
            postep("ollama")
            postep("validate")
            return sentinel

        with patch("gui.analiza_worker.analizuj_lokalnie", side_effect=fake_llm):
            job.run()
        self.assertEqual(events, [
            (7, "prepare"), (7, "ollama"), (7, "validate"),
        ])
        self.assertEqual(done, [(7, sentinel)])
        self.assertFalse(job.przerwij.is_set())

    def test_anulowanie_przed_startem_nie_wysyla_etapow(self):
        job = ZadanieAnalizy(4, "FIKCYJNE", ["Inne"], "demo:1")
        stages, cancelled = [], []
        job.sygnaly.etap.connect(lambda doc, stage: stages.append(stage))
        job.sygnaly.anulowano.connect(lambda doc: cancelled.append(doc))
        job.przerwij.set()
        with patch("gui.analiza_worker.analizuj_lokalnie") as llm:
            job.run()
        llm.assert_not_called()
        self.assertEqual(cancelled, [4])
        self.assertEqual(stages, [])


if __name__ == "__main__":
    unittest.main()
