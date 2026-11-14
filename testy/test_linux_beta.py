# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Beta: archiwum musi zawierać kod/migracje/licencje, nigdy prywatną bazę."""
from __future__ import annotations

import hashlib
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools.build_linux_beta import ARCHIVE_NAME, ARCHIVE_ROOT, ROOT, build, manifest
from wersja import __version__, DISPLAY_VERSION


class TestLinuxBeta(unittest.TestCase):
    def test_wersjonowanie(self):
        self.assertEqual(__version__, "0.1.0b1")
        self.assertIn("Beta", DISPLAY_VERSION)
        self.assertEqual(ARCHIVE_NAME, f"swistak-linux-{__version__}-source.tar.gz")

    def test_pakiet_kompletny_i_bez_prywatnych_danych(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = build(Path(tmp))
            self.assertTrue(archive.is_file())
            with tarfile.open(archive, mode="r:gz") as tar:
                names = {x.name for x in tar.getmembers()}
                def file(name: str) -> bytes:
                    member = tar.getmember(f"{ARCHIVE_ROOT}/{name}")
                    self.assertTrue(member.isfile())
                    return tar.extractfile(member).read()

                needed = (
                    "main.py", "wersja.py", "instaluj.sh", "start.sh",
                    "uruchom.sh", "requirements.txt", "i18n/pl.json",
                    "i18n/en.json", "assets/branding/swistak-banner.jpeg",
                    "baza/schemat/001_start.sql",
                    "baza/schemat/002_numer_konta.sql",
                    "baza/schemat/003_platnosci_wycofanie.sql",
                    "baza/schemat/004_plan_rachunkow.sql",
                    "baza/schemat/005_cykle_audyt.sql",
                    "ai_core/contracts.py", "ai_core/gateway.py",
                    "ai_core/hybrid.py", "ai_core/ollama.py",
                    "ai_core/router.py", "ai_core/orchestrator.py",
                    "docs/ai_core/contracts_v1.schema.json",
                    "docs/ai_core/tools_v1.json",
                    "LICENSE", "NOTICE.md", "THIRD_PARTY_LICENSES.md",
                )
                for name in needed:
                    with self.subTest(name=name):
                        self.assertIn(f"{ARCHIVE_ROOT}/{name}", names)
                        self.assertEqual(file(name), manifest()[name].read_bytes())
                for member in tar.getmembers():
                    self.assertTrue(member.name.startswith(ARCHIVE_ROOT + "/"))
                    self.assertTrue(member.isfile())
                    self.assertFalse(member.issym())
                    self.assertFalse(member.islnk())
                    self.assertFalse(any(piece.startswith(".") for piece in
                                         Path(member.name).parts))
                    self.assertNotIn(".venv", member.name)
                    self.assertNotIn("settings.json", member.name)
                    self.assertNotIn("kopie_migracji", member.name)
                    self.assertNotIn("Swistak-Test", member.name)
                    self.assertFalse(member.name.endswith((".pdf", ".db", ".sqlite3", ".webp")))
                for name in ("start.sh", "instaluj.sh", "uruchom.sh"):
                    self.assertTrue(tar.getmember(f"{ARCHIVE_ROOT}/{name}").mode & 0o111)

    def test_archiwum_powtarzalne(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = hashlib.sha256(build(Path(a)).read_bytes()).hexdigest()
            second = hashlib.sha256(build(Path(b)).read_bytes()).hexdigest()
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
