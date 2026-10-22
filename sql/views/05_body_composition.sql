-- One row per day; if there are several weigh-ins, the latest one wins.
-- Garmin stores weight and masses in grams.
CREATE OR REPLACE VIEW `garmin.body_composition` AS
SELECT
  date,
  ROUND(LAX_FLOAT64(w.weight) / 1000, 2)     AS weight_kg,
  ROUND(LAX_FLOAT64(w.bmi), 1)               AS bmi,
  ROUND(LAX_FLOAT64(w.bodyFat), 1)           AS body_fat_pct,
  ROUND(LAX_FLOAT64(w.muscleMass) / 1000, 2) AS muscle_mass_kg,
  ROUND(LAX_FLOAT64(w.boneMass) / 1000, 2)   AS bone_mass_kg,
  ROUND(LAX_FLOAT64(w.bodyWater), 1)         AS body_water_pct
FROM `garmin_raw.raw_body_composition`,
  UNNEST(JSON_QUERY_ARRAY(payload)) AS w
QUALIFY ROW_NUMBER() OVER (PARTITION BY date ORDER BY LAX_INT64(w.date) DESC) = 1;
