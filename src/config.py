"""Constants for the Garmin → BigQuery pipeline. See CLAUDE.md."""
import os
from pathlib import Path

_PROJECT_ENV = Path(__file__).resolve().parent.parent / "project.env"


def _load_project_env() -> None:
    """Load KEY=VALUE pairs from project.env (if present) without overriding real env vars."""
    if not _PROJECT_ENV.exists():
        return
    for line in _PROJECT_ENV.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_project_env()

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
if not GCP_PROJECT_ID:
    raise SystemExit("GCP_PROJECT_ID is not set. Copy project.env.example to project.env and fill it in.")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID)  # quiets google-auth project lookup
BQ_LOCATION = os.getenv("BQ_LOCATION", "EU")
RAW_DATASET = "garmin_raw"
VIEWS_DATASET = "garmin"

# Garmin tokens live in Secret Manager (source of truth, CI writes refreshed tokens back).
# The local directory is a working copy the library reads/writes during a run.
TOKENS_SECRET = "garmin-tokens"
TOKENS_VERSIONS_TO_KEEP = 3  # latest (enabled) + 2 disabled for rollback; older are destroyed
GARMIN_TOKEN_DIR = Path(os.getenv("GARMIN_TOKEN_DIR", "~/.garminconnect")).expanduser()
GARMIN_TOKEN_FILE = GARMIN_TOKEN_DIR / "garmin_tokens.json"

TOKENS_EXPIRED_MSG = (
    "Garmin tokens expired — run `python garmin_sync.py login` and "
    "`scripts/export_tokens.sh` locally, then re-run the workflow."
)

# Endpoint short names (used by --only) → raw table. Order = extraction order.
ENDPOINTS = {
    "daily_summary": "raw_daily_summary",
    "sleep": "raw_sleep",
    "hrv": "raw_hrv",
    "stress": "raw_stress",
    "body_battery": "raw_body_battery",
    "heart_rate": "raw_heart_rate",
    "respiration": "raw_respiration",
    "spo2": "raw_spo2",
    "training_readiness": "raw_training_readiness",
    "activities": "raw_activities",
    "body_composition": "raw_body_composition",
}

DEFAULT_SYNC_DAYS = 3
REQUEST_INTERVAL_S = 1.0  # throttle: ~1 request/sec
MAX_429_RETRIES = 5
CHECKPOINT_FILE = Path(__file__).resolve().parent.parent / "state" / "checkpoint.json"
