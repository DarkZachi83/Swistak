# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 8 — test wydania i przepływu AI Core 1.0.

Wyłącznie syntetyczne faktury, brak internetu, brak prawdziwej Ollamy.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPainter, QPdfWriter

from ai_core.gateway import ToolGateway
from ai_core.hybrid import HybridAgent
from ai_core.ollama import OllamaProvider
from ai_core.errors import InvalidResponse
from tools.audyt_ai_core import REQUIRED_RUNTIME, run_audit
from tools.build_linux_beta import ARCHIVE_ROOT, build
from tools.build_linux_binary import BINARY_DATA
from uslugi.analiza_ai_core import analizuj_przez_ai_core
from uslugi.analiza_llm import POLA
from uslugi.finanse import Finanse
from uslugi.historia import HistoriaRozliczen
from uslugi.odczyt_pdf import odczytaj_pdf
from uslugi.rachunki import DaneRachunku, RejestrRachunkow


FAKE_INVOICE_TEXT = (
    "FAKTURA DEMO — tylko dane syntetyczne\n"
    "Sprzedawca: Syntetyczna Energia DEMO\n"
    "Numer faktury: DEMO-10-2026\n"
    "Kwota do zapłaty: 174,80 PLN\n"
    "Termin płatności: 2026-11-06\n"
    "Okres rozliczeniowy: 10/2026\n"
    "Usługa: energia\n"
)


class FakeExtraction:
    is_local = True

    def __init__(self):
        self.models = []

    def generate_structured(self, *, task_id, model_id, messages, schema, timeout):
        self.models.append(model_id)
        self._json(schema)
        result = {name: {"wartosc": None, "dowod": None} for name in POLA}
        result["dostawca"] = {
            "wartosc": "Syntetyczna Energia DEMO",
            "dowod": "Sprzedawca: Syntetyczna Energia DEMO",
        }
        result["kwota_do_zaplaty"] = {
            "wartosc": "174,80",
            "dowod": "Kwota do zapłaty: 174,80 PLN",
        }
        result["termin_platnosci"] = {
            "wartosc": "2026-11-06",
            "dowod": "Termin płatności: 2026-11-06",
        }
        result["waluta"] = {"wartosc": "PLN", "dowod": "174,80 PLN"}
        result["kategoria_sugerowana"] = {"wartosc": "Energia", "dowod": "Usługa: energia"}
        result["okres_od"] = {
            "wartosc": "10/2026", "dowod": "Okres rozliczeniowy: 10/2026",
        }
        result["okres_do"] = {
            "wartosc": "10/2026", "dowod": "Okres rozliczeniowy: 10/2026",
        }
        return result

    @staticmethod
    def _json(schema):
        # Właściwa usługa używa tego samego formatu JSON Schema co Etap 4.
        assert "required" in schema and "kwota_do_zaplaty" in schema["required"]


class OfflineProvider:
    is_local = True

    def health_check(self, model):
        return False


class TestStage8Release(unittest.TestCase):
    def test_release_audit_validates_local_only_and_read_only_contract(self):
        result = run_audit()
        self.assertTrue(result["local_only"])
        self.assertEqual(result["read_only_tools"], 12)
        self.assertEqual(result["runtime_files"], len(REQUIRED_RUNTIME))
        self.assertFalse(result["private_documents_read"])

    def test_source_archive_imports_ai_core_in_isolated_python(self):
        # Sprawdza prawdziwy plik .tar.gz, nie tylko kod źródłowy buildera.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = build(base / "dist")
            dest = base / "isolated"
            dest.mkdir()
            with tarfile.open(archive, "r:gz") as tar:
                names = {item.name for item in tar.getmembers()}
                for path in REQUIRED_RUNTIME:
                    self.assertIn(ARCHIVE_ROOT + "/" + path, names)
                # Wyodrębnij do pustego folderu, aby import nie mógł
                # przypadkiem użyć oryginalnego repozytorium.
                for member in tar.getmembers():
                    if not member.isfile():
                        raise AssertionError("Pakiet źródłowy zawiera nie-plik")
                    relative = Path(member.name).relative_to(ARCHIVE_ROOT)
                    target = dest / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
            cmd = (
                "import sys; from pathlib import Path; "
                "sys.path.insert(0, sys.argv[1]); "
                "from ai_core.contracts import analysis_schema; "
                "from ai_core.gateway import ToolGateway; "
                "from ai_core.ollama import OllamaProvider; "
                "assert 'findings' in analysis_schema()['properties']; "
                "g=ToolGateway(Path(sys.argv[1])/'missing.sqlite3'); "
                "assert len(g.descriptors(['invoice.search']))==1; "
                "assert OllamaProvider().is_local"
            )
            run = subprocess.run(
                [sys.executable, "-I", "-c", cmd, str(dest)],
                cwd=dest, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertFalse((dest / "swistak.sqlite3").exists())

    def test_binary_release_has_schema_data_but_no_private_data(self):
        binaries = [x[0] for x in BINARY_DATA]
        self.assertIn("docs/ai_core/contracts_v1.schema.json", binaries)
        self.assertIn("docs/ai_core/tools_v1.json", binaries)
        self.assertFalse(any(".sqlite3" in x or ".pdf" in x for x in binaries))

    def test_contract_rejects_remote_and_external_ollama_addresses(self):
        for endpoint in ("https://api.example.org", "http://example.org:11434",
                         "http://localhost:11434/evil", "http://x@127.0.0.1:11434"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                OllamaProvider(endpoint)


class TestStage8SyntheticEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.register = RejestrRachunkow(self.root / "synthetic-private")
        self.finance = Finanse(self.register.db)
        self.history = HistoriaRozliczen(self.register.db)
        self.category = int(self.register.kategorie()[0]["id"])
        document = self.root / "WYŁĄCZNIE-SYNTETYCZNE.pdf"
        document.write_bytes(b"%PDF-1.4\n% synthetic document\n%%EOF")
        self.document_id, _ = self.register.importuj_pdf(document)
        self.path = self.register.katalog / "swistak.sqlite3"

    def tearDown(self):
        self.register.zamknij()
        self.temp.cleanup()

    def test_real_synthetic_pdf_text_is_read_before_ai_without_ocr_or_auto_save(self):
        # Test całego toru pliku: prawdziwy PDF Qt → warstwa tekstowa
        # → schemat sugestii LLM; nie nadpisuj bazy.
        pdf_path = self.root / "synthetic-text-layer.pdf"
        writer = QPdfWriter(str(pdf_path))
        writer.setResolution(72)
        painter = QPainter(writer)
        self.assertTrue(painter.isActive())
        painter.drawText(100, 150, "FAKTURA SYNTETYCZNA / NIE JEST RACHUNKIEM")
        painter.drawText(100, 185, "KWOTA FIKCYJNA: 90 PLN")
        self.assertTrue(painter.end())
        with patch("uslugi.odczyt_pdf._uruchom_ocr") as fallback:
            text = odczytaj_pdf(pdf_path, z_ocr=True).tekst_dla_llm
        fallback.assert_not_called()
        self.assertIn("FAKTURA", text)
        fake = FakeExtraction()
        result = analizuj_przez_ai_core(
            text, ["Energia", "Inne"], "local-demo",
            provider=fake, timeout=5,
        )
        # Model zwrócił 174,80 mimo że dokument zawiera 90 PLN;
        # Świstak musi oznaczyć taką sugestię jako niepotwierdzoną.
        self.assertFalse(result.oceny["kwota_do_zaplaty"].poprawne)
        self.assertEqual(self.register.db.execute(
            "SELECT COUNT(*) FROM rachunki"
        ).fetchone()[0], 0)

    def test_full_lifecycle_ai_suggestion_requires_manual_save_and_payment(self):
        fake = FakeExtraction()
        result = analizuj_przez_ai_core(
            FAKE_INVOICE_TEXT, ["Energia", "Inne"],
            model="local-main-demo", model_ekstrakcji="special-demo",
            provider=fake, timeout=5,
        )
        self.assertEqual(fake.models, ["special-demo"])
        self.assertEqual(result.oceny["kwota_do_zaplaty"].wartosc, "174,80")
        self.assertTrue(result.oceny["kwota_do_zaplaty"].poprawne)

        # AI nie zapisała faktury ani nie uznała jej za opłaconą.
        self.assertEqual(self.register.db.execute(
            "SELECT COUNT(*) FROM rachunki"
        ).fetchone()[0], 0)
        self.assertEqual(self.register.db.execute(
            "SELECT COUNT(*) FROM dziennik_zdarzen"
        ).fetchone()[0], 0)

        invoice_id = self.register.zapisz_rachunek(DaneRachunku(
            dokument_id=self.document_id,
            dostawca=result.oceny["dostawca"].wartosc,
            numer="DEMO-10-2026",
            kwota=result.oceny["kwota_do_zaplaty"].wartosc,
            kategoria_id=self.category,
            data_wystawienia="2026-11-01",
            termin_platnosci="2026-11-06",
            okres_od="2026-10-01",
            okres_do="2026-10-31",
            status="do_zaplaty",
        ))
        self.assertEqual(self.register.rachunek(invoice_id)["kwota_grosze"], 17480)
        self.assertEqual(self.register.rachunek(invoice_id)["status"], "do_zaplaty")

        agent = HybridAgent(
            self.path, "offline-model", reference_date="2026-11-14",
            provider_factory=lambda: OfflineProvider(),
        )
        report = agent.run("manual")
        self.assertEqual(report.model_status, "local_only")
        self.assertEqual(report.summary["unpaid_grosze"], 17480)
        self.assertEqual(report.summary["overdue"], 1)
        self.assertFalse(report.proposals)
        self.assertEqual(self.register.rachunek(invoice_id)["status"], "do_zaplaty")

        # Komplet dokumentów nie oznacza zapłaty.
        self.finance.potwierdz_kompletnosc(
            "2026-10", dzisiaj="2026-11-14"
        )
        state = self.history.miesiac("2026-10", dzisiaj="2026-11-14")
        self.assertTrue(state["documents_confirmed"])
        self.assertFalse(state["closed"])

        # Dopiero człowiek potwierdza realną datę płatności.
        self.finance.ustaw_oplacona(invoice_id, "2026-11-13")
        self.assertTrue(self.history.miesiac(
            "2026-10", dzisiaj="2026-11-14"
        )["closed"])
        self.assertEqual(self.history.miesiac(
            "2026-11", dzisiaj="2026-11-14"
        )["payments_in_month_grosze"], 17480)
        self.assertEqual(HybridAgent(
            self.path, "offline-model", reference_date="2026-11-14",
            provider_factory=lambda: OfflineProvider(),
        ).run("manual").summary["unpaid_grosze"], 0)

    def test_gateway_rejects_attempted_write_and_retains_invoice(self):
        invoice_id = self.register.zapisz_rachunek(DaneRachunku(
            dokument_id=self.document_id, dostawca="DEMO",
            numer="DEMO/10", kwota="37,40", kategoria_id=self.category,
            termin_platnosci="2026-11-06", status="do_zaplaty",
        ))
        gateway = ToolGateway(self.path)
        agent = HybridAgent(
            self.path, "offline-demo", reference_date="2026-11-14",
            provider_factory=lambda: OfflineProvider(),
        )
        task = agent._task("change", invoice_id, gateway.revision(), tools=True)
        with gateway.session(task) as session:
            call = {
                "contract_version": "1.0", "task_id": task["task_id"],
                "call_id": "forbidden-write", "tool_name": "mark_paid",
                "tool_version": "1.0", "arguments": {"invoice_id": invoice_id},
                "data_revision": task["data_revision"],
            }
            response = session.execute(call)
            self.assertEqual(response["status"], "error")
            self.assertEqual(response["error"]["code"], "permission_denied")
        self.assertEqual(self.register.rachunek(invoice_id)["status"], "do_zaplaty")

    def test_no_sqlite_schema_upgrade_required_for_ai_core_8(self):
        expected = ["001_start.sql", "002_numer_konta.sql",
                    "003_platnosci_wycofanie.sql", "004_plan_rachunkow.sql",
                    "005_cykle_audyt.sql"]
        schema = Path(__file__).resolve().parents[1] / "baza" / "schemat"
        found = sorted(x.name for x in schema.glob("[0-9][0-9][0-9]_*.sql"))
        self.assertEqual(found, expected)


if __name__ == "__main__":
    unittest.main()
