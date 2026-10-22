-- One row per activity. duration = elapsed time in the activity (s); distance in m.
CREATE OR REPLACE VIEW `garmin.activities` AS
SELECT
  LAX_INT64(payload.activityId)                                   AS activity_id,
  date,
  PARSE_DATETIME('%Y-%m-%d %H:%M:%S', LAX_STRING(payload.startTimeLocal)) AS start_time_local,
  LAX_STRING(payload.activityType.typeKey)                        AS type,
  LAX_STRING(payload.activityName)                                AS name,
  ROUND(LAX_FLOAT64(payload.duration) / 60, 1)                    AS duration_min,
  ROUND(LAX_FLOAT64(payload.movingDuration) / 60, 1)              AS moving_duration_min,
  ROUND(LAX_FLOAT64(payload.distance) / 1000, 2)                  AS distance_km,
  LAX_INT64(payload.averageHR)                                    AS avg_hr,
  LAX_INT64(payload.maxHR)                                        AS max_hr,
  LAX_INT64(payload.calories)                                     AS kcal,
  ROUND(LAX_FLOAT64(payload.elevationGain), 0)                    AS elevation_gain_m,
  ROUND(LAX_FLOAT64(payload.aerobicTrainingEffect), 1)            AS training_effect,
  ROUND(LAX_FLOAT64(payload.anaerobicTrainingEffect), 1)          AS anaerobic_training_effect,
  LAX_STRING(payload.trainingEffectLabel)                         AS training_effect_label
FROM `garmin_raw.raw_activities`;
