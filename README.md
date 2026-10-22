# Garmin → BigQuery → MCP (template)

Personal pipeline that syncs Garmin Connect health data, activities and body composition into BigQuery three times a day. Claude and ChatGPT can then query it through Google's managed BigQuery MCP server, read-only.

- **Start here (human guide, Spanish):** [`GUIA.md`](GUIA.md)
- **Build spec for Claude Code:** [`CLAUDE.md`](CLAUDE.md). Open Claude Code in your copy of this repo and ask it to follow CLAUDE.md from phase P0.

## How to use this template

1. **Use this template → Create a new repository**, and make it **Private**.
2. Clone it, open Claude Code in the folder and paste:
   > Read CLAUDE.md. Follow the phases in order, stop at every [STOP: HUMANO], and ask me before any login, cloud resource creation or anything touching credentials.
3. Claude Code fills in `project.env` (copied from `project.env.example`) and walks you through the rest.

## What's inside

| Piece | Where |
|---|---|
| CLI (login, sync, backfill, views) | `garmin_sync.py`, `src/` |
| Raw tables (untouched JSON, idempotent MERGE) | `sql/00_create_raw_tables.sql`, `src/load.py` |
| Clean views + column descriptions for MCP | `sql/views/` |
| GCP setup: datasets, service account, Workload Identity Federation, Secret Manager, MCP read-only deny policy | `scripts/bootstrap_gcp.sh`, `scripts/mcp_readonly_deny_policy.json` |
| Sync 3×/day at local time, DST-safe | `.github/workflows/daily-sync.yml` |
| Per-person settings (not secrets) | `project.env` |

## Security model

- **No service account keys.** GitHub Actions authenticates with Workload Identity Federation, trusted only for your repo ID on `main`. Local runs impersonate the service account.
- **Garmin tokens only, never the password.** They live in GCP Secret Manager, and refreshed tokens are written back on every run.
- **The service account can write only to the two pipeline datasets.**
- **MCP is read-only.** A deny policy blocks every MCP tool not annotated as read-only (`execute_sql`, `cancel_job`).
- **No GitHub Secrets.** Only repository variables.

## Commands

All commands run with `.venv/bin/python`.

| Command | What it does |
|---|---|
| `garmin_sync.py login` | Interactive Garmin login + MFA (run it yourself in a terminal) |
| `scripts/export_tokens.sh` | Upload local Garmin tokens to Secret Manager |
| `garmin_sync.py sync [--days N] [--only a,b] [--dry-run]` | Sync the last N days (default 3) |
| `garmin_sync.py backfill --start YYYY-MM-DD [--end YYYY-MM-DD]` | Historical load, monthly chunks, resumable |
| `garmin_sync.py views` | Recreate views and apply descriptions |
| `scripts/bootstrap_gcp.sh` | (Re)apply all GCP setup; idempotent |

## Runbook

| Situation | What to do |
|---|---|
| Sync failed: "Garmin tokens expired" | `garmin_sync.py login` → `scripts/export_tokens.sh` → re-run the workflow |
| Sync failed: other error | Check the Actions log; re-run via `workflow_dispatch`; if Garmin changed an endpoint, upgrade `garminconnect` and test with `--dry-run` |
| Gap in data | `garmin_sync.py backfill --start <from> --end <to>` |
| GCP auth failed in Actions | Run on `main`? Repo variables correct? Repo renamed? Update `project.env` and re-run `bootstrap_gcp.sh` |
| Local auth expired | `gcloud auth application-default login --impersonate-service-account=garmin-sync@<PROJECT_ID>.iam.gserviceaccount.com` |
| MCP connector asks to reconnect | Sign in to Google again in the connector |

Built with Claude Code. Uses the unofficial [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) library; Garmin can change its API without notice.
