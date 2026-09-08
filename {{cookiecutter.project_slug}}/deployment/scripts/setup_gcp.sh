#!/usr/bin/env bash
# One-time GCP project bootstrap for {{cookiecutter.project_name}}.
#
# Run once per GCP project — once for dev, once for prod, each pointed at its
# own GOOGLE_CLOUD_PROJECT. Safe to re-run — checks before creating.
#
# Usage:
#   ./deployment/scripts/setup_gcp.sh dev     # bootstrap the dev project
#   ./deployment/scripts/setup_gcp.sh prod    # bootstrap the prod project (default)
set -euo pipefail

GH_ENVIRONMENT="${1:-prod}"
case "$GH_ENVIRONMENT" in
  dev|prod) ;;
  *)
    echo "Usage: $0 [dev|prod]  (defaults to prod)" >&2
    exit 1
    ;;
esac

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT in .env or export it first}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-europe-west1}"
SA_NAME="agent-engine-sa"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
BUCKET="${GCS_STAGING_BUCKET:-${PROJECT}-agent-staging}"

echo "=== GCP Bootstrap: {{cookiecutter.project_name}} ($GH_ENVIRONMENT) ==="
echo "  Project:  $PROJECT"
echo "  Location: $LOCATION"
echo "  SA:       $SA_EMAIL"
echo "  Bucket:   gs://$BUCKET"
echo ""

# Enable required APIs
echo "> Enabling APIs..."
gcloud services enable \
  aiplatform.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  --project="$PROJECT"

# Create service account (idempotent)
echo "> Creating service account..."
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" &>/dev/null; then
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="Agent Engine SA for {{cookiecutter.project_name}}" \
    --project="$PROJECT"
else
  echo "  Service account already exists, skipping."
fi

# Grant IAM roles
echo "> Granting IAM roles..."
for ROLE in roles/aiplatform.user roles/logging.logWriter roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE" \
    --condition=None \
    --quiet
done

# Allow the agent's runtime identity to be assumed. deploy.py passes
# service_account=$SA_EMAIL to agent_engines.create/update, and whoever runs the
# deploy needs actAs on that SA for Vertex to accept it. These bindings are on the
# SA resource itself, not the project. Two principals need it:
#
#   - the SA itself, which is how CI authenticates (GCP_SA_KEY in deploy.yml)
#   - whoever runs this bootstrap, who is the likely local deployer. Without it,
#     their first `make deploy-dev` fails with PermissionDenied on actAs *after*
#     pickling and uploading the agent -- a confusing way to learn about an IAM
#     prerequisite. Not an escalation: this account just created the SA and granted
#     it three project roles, and this binding covers one service account.
#
# Teammates who also deploy locally need adding by hand:
#   gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
#     --member="user:them@example.com" --role=roles/iam.serviceAccountUser \
#     --project="$PROJECT"
echo "> Granting actAs on the runtime service account..."
ACT_AS_MEMBERS=("serviceAccount:$SA_EMAIL")

# `|| true` because `set -e` would abort here when no account is configured, and
# get-value reports an unset value as either empty or the literal "(unset)".
DEPLOYER="$(gcloud config get-value account 2>/dev/null || true)"
case "$DEPLOYER" in
  "" | "(unset)" | "$SA_EMAIL")
    # Nothing to add: no configured account, or it is the SA already covered above.
    ;;
  *.iam.gserviceaccount.com)
    ACT_AS_MEMBERS+=("serviceAccount:$DEPLOYER")
    ;;
  *)
    ACT_AS_MEMBERS+=("user:$DEPLOYER")
    ;;
esac

for MEMBER in "${ACT_AS_MEMBERS[@]}"; do
  echo "  $MEMBER"
  gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --member="$MEMBER" \
    --role="roles/iam.serviceAccountUser" \
    --project="$PROJECT" \
    --condition=None \
    --quiet
done

# Create GCS staging bucket (idempotent)
echo "> Creating staging bucket..."
if ! gsutil ls "gs://$BUCKET" &>/dev/null; then
  gsutil mb -p "$PROJECT" -l "$LOCATION" "gs://$BUCKET"
  gsutil iam ch "serviceAccount:${SA_EMAIL}:roles/storage.objectAdmin" "gs://$BUCKET"
else
  echo "  Bucket already exists, skipping."
fi

# Generate SA key for GitHub Actions
echo "> Generating service account key..."
KEY_FILE="gcp-sa-key.json"
gcloud iam service-accounts keys create "$KEY_FILE" \
  --iam-account="$SA_EMAIL" \
  --project="$PROJECT"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Create the '$GH_ENVIRONMENT' GitHub Environment if it doesn't exist yet"
echo "(Settings > Environments > New environment), then add the following as its"
echo "ENVIRONMENT secrets (not repository secrets — dev and prod must not share these):"
echo ""
echo "  GCP_SA_KEY           = $(cat "$KEY_FILE" | base64 | tr -d '\n')"
echo "  GOOGLE_CLOUD_PROJECT = $PROJECT"
echo ""
echo "Add the following as '$GH_ENVIRONMENT' environment variables:"
echo "  GOOGLE_CLOUD_LOCATION = $LOCATION"
echo "  MODEL_PROVIDER        = google"
echo ""
echo "Not needed -- deploy.py derives these from GOOGLE_CLOUD_PROJECT. Set them only"
echo "if you renamed the bucket or the service account:"
echo "  GCS_STAGING_BUCKET           = $BUCKET"
echo "  AGENT_ENGINE_SERVICE_ACCOUNT = $SA_EMAIL"
echo ""
echo "(AGENT_ENGINE_RESOURCE_NAME is an environment variable too — add it after this"
echo "environment's first deploy, once deploy.yml prints the created resource name.)"
echo ""
echo "IMPORTANT: Delete $KEY_FILE after copying the value above."
echo "  rm $KEY_FILE"
echo ""
echo "Update your .env file with:"
cat <<ENV
GOOGLE_CLOUD_PROJECT=$PROJECT
GOOGLE_CLOUD_LOCATION=$LOCATION
MODEL_PROVIDER=google
ENV
echo ""
echo "(The staging bucket and runtime service account are derived from the project id;"
echo " add GCS_STAGING_BUCKET or AGENT_ENGINE_SERVICE_ACCOUNT only to override them.)"
