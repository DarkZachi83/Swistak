#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")" && pwd -P)"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo "Świstak Beta: najpierw uruchom ./instaluj.sh (raz)." >&2
    exit 2
fi
exec "$ROOT/uruchom.sh" "$@"
