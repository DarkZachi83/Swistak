# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Uruchamianie w worktree bez kopiowania .venv (bez prawdziwego Qt/SQLite)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "uruchom.sh"


@unittest.skipUnless(shutil.which("bash"), "Test dotyczy Linux/Bash")
class TestUruchomLinux(unittest.TestCase):
    def _prepare(self, root: Path) -> None:
        root.mkdir()
        shutil.copyfile(SOURCE, root / "uruchom.sh")
        (root / "main.py").write_text("# Demo\n", encoding="utf-8")

    def _python(self, root: Path) -> Path:
        file = root / ".venv" / "bin" / "python"
        file.parent.mkdir(parents=True)
        file.write_text(
            "#!/usr/bin/env bash\n"
            'if [[ "$1" == "-c" ]]; then exit 0; fi\n'
            'printf "PWD=%s\\n" "$PWD"\n'
            'printf "DATA=%s\\n" "$SWISTAK_DATA_DIR"\n'
            'printf "PYTHON=%s\\n" "$0"\n'
            'printf "ARG=%s\\n" "$@"\n',
            encoding="utf-8",
        )
        file.chmod(0o755)
        return file

    def _run(self, root: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(HOME=str(home), XDG_DATA_HOME=str(home / "xdg"))
        env.pop("SWISTAK_DATA_DIR", None)
        return subprocess.run(
            ["bash", str(root / "uruchom.sh"), *args],
            cwd=home,
            env=env,
            capture_output=True, text=True, timeout=15,
            check=False,
        )

    def test_help_no_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            self._prepare(root)
            result = self._run(root, Path(tmp), "--help")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--test", result.stdout)

    def test_missing_venv_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            self._prepare(root)
            result = self._run(root, Path(tmp))
            self.assertEqual(result.returncode, 2)
            self.assertIn("python3 -m venv .venv", result.stderr)

    def test_local_venv_test_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Swistak-demo"
            self._prepare(root)
            self._python(root)
            result = self._run(root, Path(tmp), "--test", "faktura-test.pdf")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Swistak-Test-Swistak-demo", result.stdout)
            self.assertIn(f"PWD={root}", result.stdout)
            self.assertIn(f"ARG={root / 'main.py'}", result.stdout)
            self.assertIn("ARG=faktura-test.pdf", result.stdout)

    @unittest.skipUnless(shutil.which("git"), "Test wymaga Git")
    def test_worktree_finds_main_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Swistak"
            work = Path(tmp) / "Swistak-menu"
            self._prepare(root)
            exe = self._python(root)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "main.py", "uruchom.sh"], check=True)
            subprocess.run(
                ["git", "-C", str(root), "-c", "user.name=Test",
                 "-c", "user.email=test@example.invalid", "commit", "-qm", "test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "worktree", "add", "-qb",
                 "feature/menu", str(work)],
                check=True,
            )
            result = self._run(work, Path(tmp), "--test")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"PYTHON={exe}", result.stdout)
            self.assertIn(f"PWD={work}", result.stdout)
            self.assertIn("Swistak-Test-feature_menu", result.stdout)


if __name__ == "__main__":
    unittest.main()
