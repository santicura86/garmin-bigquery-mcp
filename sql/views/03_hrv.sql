CREATE OR REPLACE VIEW `garmin.hrv` AS
SELECT
  date,
  LAX_INT64(payload.hrvSummary.weeklyAvg)        AS hrv_weekly_avg,
  LAX_INT64(payload.hrvSummary.lastNightAvg)     AS hrv_last_night,
  LAX_INT64(payload.hrvSummary.lastNight5MinHigh) AS hrv_last_night_5min_high,
  LAX_STRING(payload.hrvSummary.status)          AS hrv_status
FROM `garmin_raw.raw_hrv`;
