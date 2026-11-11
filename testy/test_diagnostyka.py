# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Polecenia diagnostyczne są bezpieczne dla katalogu danych użytkownika."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestDiagnostykaCLI(unittest.TestCase):
    def test_wersja_bez_tworzania_bazy(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "rachunki-prywatne"
            env = dict(os.environ, SWISTAK_DATA_DIR=str(data))
            p = subprocess.run(
                [sys.executable, str(ROOT / "main.py"), "--version"],
                cwd=td, env=env, capture_output=True, text=True,
                timeout=30, check=False,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout.strip(), "0.1.0b1")
            self.assertFalse(data.exists())

    def test_self_test_bez_sqlite_i_bez_ollamy(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "rachunki-prywatne"
            env = dict(
                os.environ,
                SWISTAK_DATA_DIR=str(data),
                QT_QPA_PLATFORM="offscreen",
            )
            p = subprocess.run(
                [sys.executable, str(ROOT / "main.py"), "--self-test"],
                cwd=td, env=env, capture_output=True, text=True,
                timeout=45, check=False,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("test binarny OK", p.stdout)
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()
