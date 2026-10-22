-- Raw tables (CLAUDE.md §6.2). Idempotent; executed by load.ensure_raw_tables().

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_daily_summary` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_sleep` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_hrv` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_stress` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_body_battery` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_heart_rate` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_respiration` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_spo2` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_training_readiness` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_activities` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;

CREATE TABLE IF NOT EXISTS `garmin_raw.raw_body_composition` (
  date DATE NOT NULL,
  record_id STRING NOT NULL,
  payload JSON,
  ingested_at TIMESTAMP NOT NULL,
  source_version STRING
)
PARTITION BY date
CLUSTER BY record_id;
