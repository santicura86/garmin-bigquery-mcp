#!/usr/bin/env bash
# GCP bootstrap for the Garmin → BigQuery pipeline (CLAUDE.md §6.1).
# Idempotent: safe to re-run. Creates no service account keys (blocked by org policy, by design).
set -euo pipefail

[ -d "$HOME/google-cloud-sdk/bin" ] && export PATH="$HOME/google-cloud-sdk/bin:$PATH"

# Per-person settings live in project.env (copy from project.env.example).
ENV_FILE="$(dirname "$0")/../project.env"
[ -f "$ENV_FILE" ] || { echo "Missing project.env (copy project.env.example and fill it in)"; exit 1; }
while IFS= read -r line || [ -n "$line" ]; do   # KEY=VALUE, '#' comments; works with macOS bash 3.2
  line="${line%%#*}"
  case "$line" in *=*) ;; *) continue ;; esac
  key="$(echo "${line%%=*}" | xargs)"; val="$(echo "${line#*=}" | xargs)"
  [ -n "$key" ] && export "$key=$val"
done < "$ENV_FILE"
for v in GCP_PROJECT_ID GCP_PROJECT_NUMBER BQ_LOCATION SECRET_LOCATION USER_EMAIL GITHUB_REPO GITHUB_REPO_ID; do
  [ -n "${!v:-}" ] || { echo "project.env: $v is empty"; exit 1; }
done

PROJECT_ID="$GCP_PROJECT_ID"
PROJECT_NUMBER="$GCP_PROJECT_NUMBER"
LOCATION="$BQ_LOCATION"
DATASETS=(garmin_raw garmin)
SA_NAME="garmin-sync"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
LOCAL_USER="$USER_EMAIL"             # impersonates the SA for local runs; signs in to MCP

GITHUB_REF="refs/heads/main"         # GITHUB_REPO_ID (numeric) guards against repo-name reuse
WIF_POOL="github"
WIF_PROVIDER="github-actions"

TOKENS_SECRET="garmin-tokens"
TOKENS_SECRET_LOCATION="$SECRET_LOCATION"

log() { echo "==> $*"; }

# --- Service account (created in P0; ensured here) ---------------------------
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
  log "Creating service account $SA_EMAIL"
  gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT_ID" --display-name "Garmin sync"
fi

log "Granting roles/bigquery.jobUser (project) to $SA_EMAIL"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:$SA_EMAIL" --role roles/bigquery.jobUser \
  --condition=None --format=none

# --- Datasets + dataset-level dataEditor -------------------------------------
for ds in "${DATASETS[@]}"; do
  if ! bq --project_id "$PROJECT_ID" show --dataset "$PROJECT_ID:$ds" >/dev/null 2>&1; then
    log "Creating dataset $ds ($LOCATION)"
    bq --project_id "$PROJECT_ID" --location "$LOCATION" mk --dataset "$PROJECT_ID:$ds"
  fi
  log "Granting roles/bigquery.dataEditor on $ds to $SA_EMAIL"
  # SQL DCL rather than `bq add-iam-policy-binding` (which needs allowlisting for datasets).
  bq --project_id "$PROJECT_ID" --location "$LOCATION" query --nouse_legacy_sql --quiet \
    "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`${PROJECT_ID}.${ds}\` TO \"serviceAccount:${SA_EMAIL}\""
done

# --- Local impersonation ------------------------------------------------------
log "Granting roles/iam.serviceAccountTokenCreator on $SA_EMAIL to $LOCAL_USER"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" --project "$PROJECT_ID" \
  --member "user:$LOCAL_USER" --role roles/iam.serviceAccountTokenCreator --format=none

# --- Workload Identity Federation (GitHub Actions) ---------------------------
log "Enabling IAM Service Account Credentials API (needed for WIF impersonation)"
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project "$PROJECT_ID"

if ! gcloud iam workload-identity-pools describe "$WIF_POOL" \
     --project "$PROJECT_ID" --location global >/dev/null 2>&1; then
  log "Creating workload identity pool $WIF_POOL"
  gcloud iam workload-identity-pools create "$WIF_POOL" \
    --project "$PROJECT_ID" --location global --display-name "GitHub Actions"
fi

WIF_CONDITION="assertion.repository_id=='${GITHUB_REPO_ID}' && assertion.repository=='${GITHUB_REPO}' && assertion.ref=='${GITHUB_REF}'"
WIF_MAPPING="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref"

if gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER" \
     --project "$PROJECT_ID" --location global --workload-identity-pool "$WIF_POOL" >/dev/null 2>&1; then
  log "Updating OIDC provider $WIF_PROVIDER"
  gcloud iam workload-identity-pools providers update-oidc "$WIF_PROVIDER" \
    --project "$PROJECT_ID" --location global --workload-identity-pool "$WIF_POOL" \
    --attribute-mapping "$WIF_MAPPING" --attribute-condition "$WIF_CONDITION"
else
  log "Creating OIDC provider $WIF_PROVIDER"
  gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
    --project "$PROJECT_ID" --location global --workload-identity-pool "$WIF_POOL" \
    --display-name "GitHub Actions" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "$WIF_MAPPING" --attribute-condition "$WIF_CONDITION"
fi

log "Granting roles/iam.workloadIdentityUser on $SA_EMAIL to $GITHUB_REPO"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" --project "$PROJECT_ID" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}" \
  --format=none

# --- Secret Manager: Garmin tokens (CI reads + writes back refreshed tokens) --
log "Enabling Secret Manager API"
gcloud services enable secretmanager.googleapis.com --project "$PROJECT_ID"

if ! gcloud secrets describe "$TOKENS_SECRET" --project "$PROJECT_ID" >/dev/null 2>&1; then
  log "Creating secret $TOKENS_SECRET ($TOKENS_SECRET_LOCATION)"
  gcloud secrets create "$TOKENS_SECRET" --project "$PROJECT_ID" \
    --replication-policy user-managed --locations "$TOKENS_SECRET_LOCATION"
fi

for role in roles/secretmanager.secretAccessor roles/secretmanager.secretVersionManager; do
  log "Granting $role on secret $TOKENS_SECRET to $SA_EMAIL"
  gcloud secrets add-iam-policy-binding "$TOKENS_SECRET" --project "$PROJECT_ID" \
    --member "serviceAccount:$SA_EMAIL" --role "$role" --format=none
done

# --- Dataset descriptions (for MCP clients; text lives in sql/views/descriptions.json) ---
for ds in "${DATASETS[@]}"; do
  desc=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['datasets'][sys.argv[2]])" \
    "$(dirname "$0")/../sql/views/descriptions.json" "$ds")
  log "Setting description on dataset $ds"
  bq --project_id "$PROJECT_ID" update --description "$desc" "$PROJECT_ID:$ds" >/dev/null
done

# --- MCP: tool access + read-only guardrail ------------------------------------
log "Granting roles/mcp.toolUser (project) to $LOCAL_USER"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "user:$LOCAL_USER" --role roles/mcp.toolUser --condition=None --format=none

# Deny policy blocking every MCP tool not annotated read-only (BigQuery: execute_sql).
# Requires roles/iam.denyAdmin (granted at org level).
if ! gcloud iam policies get mcp-read-only --kind=denypolicies \
     --attachment-point="cloudresourcemanager.googleapis.com/projects/$PROJECT_ID" >/dev/null 2>&1; then
  log "Creating deny policy mcp-read-only"
  gcloud iam policies create mcp-read-only --kind=denypolicies \
    --attachment-point="cloudresourcemanager.googleapis.com/projects/$PROJECT_ID" \
    --policy-file="$(dirname "$0")/mcp_readonly_deny_policy.json"
fi

log "Done. WIF provider: projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"
