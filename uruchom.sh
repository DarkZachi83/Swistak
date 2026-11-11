#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Linux: uruchamianie Świstaka również z git worktree, bez kopiowania .venv.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")" && pwd -P)"

usage() {
    cat <<'HELP'
Świstak — uruchamianie na Linuxie

  ./uruchom.sh                  Użyj domyślnej prywatnej bazy rachunków
  ./uruchom.sh --test           Osobna baza testowa dla tej gałęzi/worktree
  ./uruchom.sh --help           Pomoc
  ./uruchom.sh /sciezka.pdf     Otwórz wskazany PDF

Najpierw szuka .venv obok skryptu, potem w głównym drzewie Git.
Nie instaluje bibliotek i nie modyfikuje istniejącego .venv.
HELP
}

TEST=0
if [[ "$#" -gt 0 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
    usage
    exit 0
elif [[ "$#" -gt 0 && "$1" == "--test" ]]; then
    TEST=1
    shift
fi

PYTHON=""
if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
elif command -v git >/dev/null 2>&1; then
    COMMON_GIT="$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
    if [[ -n "$COMMON_GIT" ]]; then
        if [[ "$COMMON_GIT" != /* ]]; then
            COMMON_GIT="$ROOT/$COMMON_GIT"
        fi
        COMMON_GIT="$(cd -- "$COMMON_GIT" 2>/dev/null && pwd -P || true)"
        if [[ -n "$COMMON_GIT" ]]; then
            MAIN_DIR="$(dirname -- "$COMMON_GIT")"
            if [[ -x "$MAIN_DIR/.venv/bin/python" ]]; then
                PYTHON="$MAIN_DIR/.venv/bin/python"
            fi
        fi
    fi
fi

if [[ -z "$PYTHON" ]]; then
    echo "Świstak: brak .venv w bieżącym katalogu i głównym drzewie Git." >&2
    echo "W katalogu głównego projektu wykonaj:" >&2
    echo "  python3 -m venv .venv" >&2
    echo "  .venv/bin/python -m pip install -r requirements.txt" >&2
    exit 2
fi

if ! "$PYTHON" -c "import PySide6, pdfplumber, pypdfium2, pytesseract, PIL" >/dev/null 2>&1; then
    echo "Świstak: w środowisku brakuje bibliotek z requirements.txt." >&2
    echo "Zainstaluj je świadomie w wybranym środowisku:" >&2
    echo "  \"$PYTHON\" -m pip install -r \"$ROOT/requirements.txt\"" >&2
    exit 3
fi

if [[ "$TEST" -eq 1 ]]; then
    BRANCH=""
    if command -v git >/dev/null 2>&1; then
        BRANCH="$(git -C "$ROOT" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
    fi
    if [[ -z "$BRANCH" ]]; then
        BRANCH="$(basename -- "$ROOT")"
    fi
    SAFE_BRANCH="$(printf '%s' "$BRANCH" | LC_ALL=C sed 's/[^A-Za-z0-9._-]/_/g')"
    DATA_HOME="$(printenv XDG_DATA_HOME || true)"
    if [[ -z "$DATA_HOME" ]]; then
        DATA_HOME="$HOME/.local/share"
    fi
    export SWISTAK_DATA_DIR="$DATA_HOME/Swistak-Test-$SAFE_BRANCH"
    echo "Świstak — osobna baza testowa: $SWISTAK_DATA_DIR"
fi

cd -- "$ROOT"
exec "$PYTHON" "$ROOT/main.py" "$@"
