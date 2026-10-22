-- One row per day from raw_daily_summary.
-- Garmin uses negative stress values (-1/-2) for "not enough data" → NULL.
-- intensity_minutes follows Garmin's convention: moderate + 2 × vigorous.
CREATE OR REPLACE VIEW `garmin.daily_health` AS
SELECT
  date,
  LAX_INT64(payload.totalSteps)                                   AS steps,
  ROUND(LAX_FLOAT64(payload.totalDistanceMeters) / 1000, 2)       AS distance_km,
  LAX_INT64(payload.restingHeartRate)                             AS resting_hr,
  LAX_INT64(payload.minHeartRate)                                 AS min_hr,
  LAX_INT64(payload.maxHeartRate)                                 AS max_hr,
  IF(LAX_INT64(payload.averageStressLevel) < 0, NULL, LAX_INT64(payload.averageStressLevel)) AS avg_stress,
  IF(LAX_INT64(payload.maxStressLevel) < 0, NULL, LAX_INT64(payload.maxStressLevel))         AS max_stress,
  LAX_INT64(payload.bodyBatteryHighestValue)                      AS body_battery_high,
  LAX_INT64(payload.bodyBatteryLowestValue)                       AS body_battery_low,
  LAX_INT64(payload.bodyBatteryChargedValue)                      AS body_battery_charged,
  LAX_INT64(payload.bodyBatteryDrainedValue)                      AS body_battery_drained,
  LAX_INT64(payload.activeKilocalories)                           AS active_kcal,
  LAX_INT64(payload.totalKilocalories)                            AS total_kcal,
  LAX_INT64(payload.moderateIntensityMinutes)                     AS moderate_intensity_min,
  LAX_INT64(payload.vigorousIntensityMinutes)                     AS vigorous_intensity_min,
  COALESCE(LAX_INT64(payload.moderateIntensityMinutes), 0)
    + 2 * COALESCE(LAX_INT64(payload.vigorousIntensityMinutes), 0) AS intensity_minutes,
  ROUND(LAX_FLOAT64(payload.floorsAscended), 1)                   AS floors,
  LAX_INT64(payload.avgWakingRespirationValue)                    AS avg_waking_respiration,
  LAX_INT64(payload.averageSpo2)                                  AS avg_spo2
FROM `garmin_raw.raw_daily_summary`;
