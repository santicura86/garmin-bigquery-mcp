"""BigQuery load: staging table (WRITE_TRUNCATE) → MERGE on record_id → drop staging."""
import datetime as dt
import json
import logging
import uuid
from importlib.metadata import version
from pathlib import Path

from google.cloud import bigquery

from src.config import BQ_LOCATION, GCP_PROJECT_ID, RAW_DATASET, VIEWS_DATASET

log = logging.getLogger(__name__)

SOURCE_VERSION = f"garminconnect=={version('garminconnect')}"
_SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

# Staging keeps payload as STRING; MERGE parses it, so ingestion never depends on JSON load quirks.
_STAGING_SCHEMA = [
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("record_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("payload", "STRING"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("source_version", "STRING"),
]


def client() -> bigquery.Client:
    return bigquery.Client(project=GCP_PROJECT_ID, location=BQ_LOCATION)


def ensure_raw_tables(bq: bigquery.Client) -> None:
    sql = (_SQL_DIR / "00_create_raw_tables.sql").read_text()
    bq.query(sql, job_config=bigquery.QueryJobConfig(default_dataset=f"{GCP_PROJECT_ID}.{RAW_DATASET}")).result()


def merge_rows(bq: bigquery.Client, table: str, rows: list[dict]) -> int:
    """Upsert rows into garmin_raw.<table>. Returns the number of rows staged."""
    if not rows:
        return 0
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    deduped = {r["record_id"]: r for r in rows}  # last wins
    staged = [
        {
            "date": r["date"],
            "record_id": r["record_id"],
            "payload": json.dumps(r["payload"], separators=(",", ":"), ensure_ascii=False),
            "ingested_at": now,
            "source_version": SOURCE_VERSION,
        }
        for r in deduped.values()
    ]
    target = f"{GCP_PROJECT_ID}.{RAW_DATASET}.{table}"
    staging = f"{GCP_PROJECT_ID}.{RAW_DATASET}._stg_{table}_{uuid.uuid4().hex[:8]}"
    try:
        bq.load_table_from_json(
            staged,
            staging,
            job_config=bigquery.LoadJobConfig(
                schema=_STAGING_SCHEMA,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            ),
        ).result()
        bq.query(f"""
            MERGE `{target}` T
            USING `{staging}` S
            ON T.record_id = S.record_id
            WHEN MATCHED THEN UPDATE SET
              date = S.date,
              payload = PARSE_JSON(S.payload, wide_number_mode => 'round'),
              ingested_at = S.ingested_at,
              source_version = S.source_version
            WHEN NOT MATCHED THEN INSERT (date, record_id, payload, ingested_at, source_version)
              VALUES (S.date, S.record_id, PARSE_JSON(S.payload, wide_number_mode => 'round'),
                      S.ingested_at, S.source_version)
        """).result()
    finally:
        bq.delete_table(staging, not_found_ok=True)
    return len(staged)


def deploy_views(bq: bigquery.Client) -> list[str]:
    """Create or replace every view in sql/views/ (files run in name order), then apply descriptions."""
    deployed = []
    for path in sorted((_SQL_DIR / "views").glob("*.sql")):
        bq.query(path.read_text()).result()
        deployed.append(path.stem)
    apply_descriptions(bq)
    return deployed


def apply_descriptions(bq: bigquery.Client) -> None:
    """View and column descriptions from sql/views/descriptions.json.

    They help MCP clients (Claude, ChatGPT) pick the right table and read units correctly.
    CREATE OR REPLACE VIEW drops column descriptions, so this runs after every deploy.
    Dataset descriptions need bigquery.datasets.update, which the service account doesn't
    have; scripts/bootstrap_gcp.sh sets them as the project owner.
    """
    desc = json.loads((_SQL_DIR / "views" / "descriptions.json").read_text())
    for view_id, text in desc["views"].items():
        view = bq.get_table(f"{GCP_PROJECT_ID}.{VIEWS_DATASET}.{view_id}")
        view.description = text
        view.schema = [
            bigquery.SchemaField(f.name, f.field_type, mode=f.mode,
                                 description=desc["columns"].get(f.name, f.description))
            for f in view.schema
        ]
        bq.update_table(view, ["description", "schema"])
