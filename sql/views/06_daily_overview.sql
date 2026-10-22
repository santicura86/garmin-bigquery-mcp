-- Main analysis table: one row per day with data in any source, joined by date.
CREATE OR REPLACE VIEW `garmin.daily_overview` AS
WITH activity_days AS (
  SELECT
    date,
    COUNT(*)              AS activity_count,
    SUM(duration_min)     AS activity_min,
    SUM(distance_km)      AS activity_distance_km,
    SUM(kcal)             AS activity_kcal,
    STRING_AGG(DISTINCT type, ', ' ORDER BY type) AS activity_types
  FROM `garmin.activities`
  GROUP BY date
),
days AS (
  SELECT date FROM `garmin.daily_health`
  UNION DISTINCT SELECT date FROM `garmin.sleep`
  UNION DISTINCT SELECT date FROM `garmin.hrv`
  UNION DISTINCT SELECT date FROM activity_days
  UNION DISTINCT SELECT date FROM `garmin.body_composition`
)
SELECT
  d.date,
  h.* EXCEPT (date),
  s.* EXCEPT (date),
  v.* EXCEPT (date),
  a.* EXCEPT (date),
  b.* EXCEPT (date)
FROM days d
LEFT JOIN `garmin.daily_health`     h USING (date)
LEFT JOIN `garmin.sleep`            s USING (date)
LEFT JOIN `garmin.hrv`              v USING (date)
LEFT JOIN activity_days             a USING (date)
LEFT JOIN `garmin.body_composition` b USING (date);
