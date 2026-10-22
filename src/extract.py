"""One extractor per endpoint. Each returns rows: {"date": "YYYY-MM-DD", "record_id": str, "payload": obj}.

Empty days are skipped (logged at INFO). Garmin returns a skeleton with a few metadata
fields on days without data, so emptiness is "no non-null value outside metadata keys"
(metadata sets observed from real empty-day responses).
"""
import datetime as dt
import logging
import time
from collections import defaultdict
from typing import Any, Callable

from garminconnect import Garmin, GarminConnectTooManyRequestsError

from src.config import MAX_429_RETRIES, REQUEST_INTERVAL_S

log = logging.getLogger(__name__)

Row = dict[str, Any]

_last_call = 0.0


def _call(fn: Callable, *args) -> Any:
    """Throttle to ~1 req/s; back off exponentially on HTTP 429 (max 5 retries)."""
    global _last_call
    for attempt in range(MAX_429_RETRIES + 1):
        wait = REQUEST_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        try:
            return fn(*args)
        except GarminConnectTooManyRequestsError:
            if attempt == MAX_429_RETRIES:
                raise
            backoff = 30 * 2**attempt
            log.warning("Rate limited by Garmin (429); retry %d/%d in %ds", attempt + 1, MAX_429_RETRIES, backoff)
            time.sleep(backoff)


def _days(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def _has_data(payload: Any, meta: set[str]) -> bool:
    if not payload:
        return False
    return any(v not in (None, [], {}, "") for k, v in payload.items() if k not in meta)


# Per-day endpoints: name → (fetch(api, date_str), is_non_empty(payload))
_DAILY: dict[str, tuple[Callable, Callable]] = {
    "daily_summary": (
        lambda api, d: api.get_user_summary(d),
        lambda p: _has_data(p, {"calendarDate", "displayName", "includesActivityData",
                                "includesCalorieConsumedData", "includesWellnessData",
                                "netRemainingKilocalories", "privacyProtected", "source",
                                "userProfileId", "uuid", "rule"}),
    ),
    "sleep": (
        lambda api, d: api.get_sleep_data(d),
        # dailySleepDTO always carries computed fields (sleepNeed, nextSleepNeed); require a recorded sleep.
        lambda p: bool(p) and any((p.get("dailySleepDTO") or {}).get(k)
                                  for k in ("sleepTimeSeconds", "sleepStartTimestampGMT")),
    ),
    "hrv": (
        lambda api, d: api.get_hrv_data(d),
        lambda p: bool(p) and bool(p.get("hrvSummary")),
    ),
    "stress": (
        lambda api, d: api.get_stress_data(d),
        lambda p: _has_data(p, {"calendarDate", "userProfilePK"}),
    ),
    "body_battery": (
        # Returns a one-element list for a single day; store the element.
        lambda api, d: (api.get_body_battery(d, d) or [None])[0],
        lambda p: _has_data(p, {"date", "bodyBatteryValuesArray"}),
    ),
    "heart_rate": (
        lambda api, d: api.get_heart_rates(d),
        lambda p: _has_data(p, {"calendarDate", "userProfilePK"}),
    ),
    "respiration": (
        lambda api, d: api.get_respiration_data(d),
        lambda p: _has_data(p, {"calendarDate", "userProfilePK", "respirationVersion"}),
    ),
    "spo2": (
        lambda api, d: api.get_spo2_data(d),
        lambda p: _has_data(p, {"calendarDate", "userProfilePK"}),
    ),
    "training_readiness": (
        # List of readiness snapshots for the day; store the whole list.
        lambda api, d: api.get_training_readiness(d),
        lambda p: bool(p),
    ),
}


def extract_daily(api: Garmin, name: str, start: dt.date, end: dt.date) -> list[Row]:
    fetch, non_empty = _DAILY[name]
    rows = []
    for day in _days(start, end):
        d = day.isoformat()
        payload = _call(fetch, api, d)
        if not non_empty(payload):
            log.info("%s %s: no data, skipped", name, d)
            continue
        rows.append({"date": d, "record_id": d, "payload": payload})
    return rows


def extract_activities(api: Garmin, start: dt.date, end: dt.date) -> list[Row]:
    acts = _call(api.get_activities_by_date, start.isoformat(), end.isoformat()) or []
    rows = {}
    for a in acts:
        rows[str(a["activityId"])] = {
            "date": a["startTimeLocal"][:10],
            "record_id": str(a["activityId"]),
            "payload": a,
        }
    return list(rows.values())


def extract_body_composition(api: Garmin, start: dt.date, end: dt.date) -> list[Row]:
    resp = _call(api.get_body_composition, start.isoformat(), end.isoformat()) or {}
    by_day: dict[str, list] = defaultdict(list)
    for entry in resp.get("dateWeightList") or []:
        by_day[entry["calendarDate"][:10]].append(entry)
    # 1 row/day; payload = that day's weigh-ins exactly as returned.
    return [{"date": d, "record_id": d, "payload": entries} for d, entries in sorted(by_day.items())]


def extract(api: Garmin, name: str, start: dt.date, end: dt.date) -> list[Row]:
    if name == "activities":
        return extract_activities(api, start, end)
    if name == "body_composition":
        return extract_body_composition(api, start, end)
    return extract_daily(api, name, start, end)
