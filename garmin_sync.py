"""Garmin → BigQuery sync CLI. See CLAUDE.md §8."""
import argparse
import datetime as dt
import json
import logging
import sys

from garminconnect import GarminConnectAuthenticationError

from src import auth, extract, load
from src.config import TOKENS_EXPIRED_MSG, CHECKPOINT_FILE, DEFAULT_SYNC_DAYS, ENDPOINTS, GARMIN_TOKEN_DIR

log = logging.getLogger("garmin_sync")


def _parse_only(value: str | None) -> list[str]:
    if not value:
        return list(ENDPOINTS)
    names = [n.strip() for n in value.split(",") if n.strip()]
    unknown = [n for n in names if n not in ENDPOINTS]
    if unknown:
        raise SystemExit(f"Unknown endpoint(s): {', '.join(unknown)}. Valid: {', '.join(ENDPOINTS)}")
    return names


def _run_range(api, bq, names: list[str], start: dt.date, end: dt.date, dry_run: bool) -> list[str]:
    """Extract (and load unless dry-run) every endpoint for [start, end]. Returns error messages."""
    errors = []
    for name in names:
        try:
            rows = extract.extract(api, name, start, end)
            if dry_run:
                log.info("%-20s %s..%s: %d rows (dry run, not loaded)", name, start, end, len(rows))
            else:
                n = load.merge_rows(bq, ENDPOINTS[name], rows)
                log.info("%-20s %s..%s: %d rows merged into %s", name, start, end, n, ENDPOINTS[name])
        except auth.TokensExpiredError:
            raise
        except GarminConnectAuthenticationError as e:
            raise auth.TokensExpiredError(TOKENS_EXPIRED_MSG) from e
        except Exception as e:  # one endpoint failing must not stop the others
            log.error("%s %s..%s failed: %s: %s", name, start, end, type(e).__name__, e)
            errors.append(f"{name} {start}..{end}: {type(e).__name__}")
    return errors


def _session(dry_run: bool):
    api, tokens = auth.restore_session()
    bq = None
    if not dry_run:
        bq = load.client()
        load.ensure_raw_tables(bq)
    return api, tokens, bq


def _finish(api, tokens: str, errors: list[str]) -> int:
    try:
        auth.persist_refreshed_tokens(api, tokens)
    except Exception as e:
        log.error("Could not save refreshed Garmin tokens to Secret Manager: %s", e)
        errors.append("token write-back")
    if errors:
        log.error("Finished with %d error(s): %s", len(errors), "; ".join(errors))
        return 1
    log.info("Finished without errors.")
    return 0


def cmd_login(_args) -> int:
    api = auth.interactive_login()
    print(f"Logged in as {api.display_name}. Tokens saved to {GARMIN_TOKEN_DIR}.")
    print("Next: run scripts/export_tokens.sh to upload them to Secret Manager.")
    return 0


def cmd_sync(args) -> int:
    end = dt.date.today()
    start = end - dt.timedelta(days=args.days - 1)
    names = _parse_only(args.only)
    api, tokens, bq = _session(args.dry_run)
    errors = _run_range(api, bq, names, start, end, args.dry_run)
    return _finish(api, tokens, errors)


def _month_chunks(start: dt.date, end: dt.date):
    s = start
    while s <= end:
        next_month = (s.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        e = min(next_month - dt.timedelta(days=1), end)
        yield s, e
        s = e + dt.timedelta(days=1)


def cmd_backfill(args) -> int:
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end) if args.end else dt.date.today()
    names = _parse_only(args.only)
    key = {"start": start.isoformat(), "end": end.isoformat(), "only": names}

    resume_from = start
    if CHECKPOINT_FILE.exists() and not args.dry_run:
        cp = json.loads(CHECKPOINT_FILE.read_text())
        if {k: cp.get(k) for k in key} == key and cp.get("completed_through"):
            resume_from = dt.date.fromisoformat(cp["completed_through"]) + dt.timedelta(days=1)
            log.info("Resuming backfill from checkpoint: %s", resume_from)
    if resume_from > end:
        log.info("Backfill %s..%s already complete per checkpoint.", start, end)
        return 0

    api, tokens, bq = _session(args.dry_run)
    errors: list[str] = []
    for c_start, c_end in _month_chunks(resume_from, end):
        log.info("=== Chunk %s..%s", c_start, c_end)
        chunk_errors = _run_range(api, bq, names, c_start, c_end, args.dry_run)
        tokens = auth.persist_refreshed_tokens(api, tokens)  # long runs can cross a refresh
        if chunk_errors:
            errors += chunk_errors
            log.error("Stopping backfill; checkpoint left at last fully successful chunk. Re-run to resume.")
            break
        if not args.dry_run:
            CHECKPOINT_FILE.parent.mkdir(exist_ok=True)
            CHECKPOINT_FILE.write_text(json.dumps({**key, "completed_through": c_end.isoformat()}, indent=2))
    return _finish(api, tokens, errors)


def cmd_views(_args) -> int:
    for name in load.deploy_views(load.client()):
        log.info("Deployed view from %s.sql", name)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("garminconnect", "urllib3", "google"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(prog="garmin_sync.py")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Interactive login + MFA; saves tokens locally").set_defaults(func=cmd_login)

    p = sub.add_parser("sync", help=f"Sync the last N days (default {DEFAULT_SYNC_DAYS})")
    p.add_argument("--days", type=int, default=DEFAULT_SYNC_DAYS)
    p.add_argument("--only", help=f"Comma-separated subset of: {', '.join(ENDPOINTS)}")
    p.add_argument("--dry-run", action="store_true", help="Extract and print counts; no BigQuery writes")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("backfill", help="Historical load in monthly chunks, resumable")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD (default: today)")
    p.add_argument("--only", help=f"Comma-separated subset of: {', '.join(ENDPOINTS)}")
    p.add_argument("--dry-run", action="store_true", help="Extract and print counts; no BigQuery writes")
    p.set_defaults(func=cmd_backfill)

    sub.add_parser("views", help="Create or replace the clean views in the garmin dataset").set_defaults(func=cmd_views)

    args = parser.parse_args()
    try:
        return args.func(args)
    except auth.TokensExpiredError as e:
        log.error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
