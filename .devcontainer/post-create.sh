#!/usr/bin/env bash
# Einrichtung des Dev-Containers: Entwicklungs- und Validierungs-Extras mit
# festen Versionen aus requirements-dev.txt, btc2premis selbst editierbar
# installieren. Python ist im Image bereits vorhanden.
set -euo pipefail

python3 - <<'PY'
import sys

if sys.version_info < (3, 11):
    sys.exit(
        f"btc2premis benoetigt Python >= 3.11, gefunden: {sys.version.split()[0]}"
    )
PY

python3 -m pip install --upgrade pip
python3 -m pip install --require-hashes -r requirements-dev.txt
python3 -m pip install --no-deps -e .

echo "Fertig. Naechste Schritte: 'ruff check .' und 'pytest -q'"
