#!/usr/bin/env bash
# Upload local Garmin tokens (from `garmin_sync.py login`) to Secret Manager.
# Requires ADC impersonating garmin-sync (see README). Token values are never printed.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -c "import logging; logging.basicConfig(level=logging.INFO, format='%(message)s'); from src import auth; auth.upload_local_tokens()"
