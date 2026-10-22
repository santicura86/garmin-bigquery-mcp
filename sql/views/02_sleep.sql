-- One row per night. Garmin's *Local timestamps are epoch-ms of the local wall-clock time,
-- so DATETIME(TIMESTAMP_MILLIS(...)) yields the local time; *GMT fields are true UTC instants.
CREATE OR REPLACE VIEW `garmin.sleep` AS
SELECT
  date,
  DATETIME(TIMESTAMP_MILLIS(LAX_INT64(payload.dailySleepDTO.sleepStartTimestampLocal))) AS sleep_start,
  DATETIME(TIMESTAMP_MILLIS(LAX_INT64(payload.dailySleepDTO.sleepEndTimestampLocal)))   AS sleep_end,
  TIMESTAMP_MILLIS(LAX_INT64(payload.dailySleepDTO.sleepStartTimestampGMT))            AS sleep_start_utc,
  TIMESTAMP_MILLIS(LAX_INT64(payload.dailySleepDTO.sleepEndTimestampGMT))              AS sleep_end_utc,
  DIV(LAX_INT64(payload.dailySleepDTO.sleepTimeSeconds), 60)  AS total_sleep_min,
  DIV(LAX_INT64(payload.dailySleepDTO.deepSleepSeconds), 60)  AS deep_min,
  DIV(LAX_INT64(payload.dailySleepDTO.lightSleepSeconds), 60) AS light_min,
  DIV(LAX_INT64(payload.dailySleepDTO.remSleepSeconds), 60)   AS rem_min,
  DIV(LAX_INT64(payload.dailySleepDTO.awakeSleepSeconds), 60) AS awake_min,
  LAX_INT64(payload.dailySleepDTO.sleepScores.overall.value)  AS sleep_score,
  LAX_STRING(payload.dailySleepDTO.sleepScores.overall.qualifierKey) AS sleep_quality
FROM `garmin_raw.raw_sleep`;
