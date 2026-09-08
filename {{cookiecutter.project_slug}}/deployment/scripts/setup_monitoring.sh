#!/usr/bin/env bash
# One-time Cloud Monitoring bootstrap for {{cookiecutter.project_name}}: creates a
# dashboard and two alert policies (error rate, p95 latency) against the metrics
# Vertex AI Agent Engine emits automatically under the ReasoningEngine monitored
# resource -- no instrumentation needed for these, unlike the app-level structured
# logging in agent/observability.py.
#
# Run once per GCP project (dev and prod separately, same as setup_gcp.sh). Safe
# to re-run -- updates existing resources instead of creating duplicates.
#
# Usage:
#   GOOGLE_CLOUD_PROJECT=my-project ALERT_EMAIL=oncall@example.com \
#     bash deployment/scripts/setup_monitoring.sh
#
# Optional env vars:
#   ALERT_EMAIL            Email address for the notification channel
#   SLACK_CHANNEL           Slack channel name, e.g. "#agent-alerts" (requires SLACK_BOT_TOKEN)
#   SLACK_BOT_TOKEN         Slack bot token (xoxb-...) with chat:write scope
#
# Rate-limit / quota alerting is not covered here: Vertex AI doesn't expose a
# per-agent quota metric to threshold on. Configure that separately via
# Cloud Console -> IAM & Admin -> Quotas -> Create Alert.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT in .env or export it first}"
MONITORING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../monitoring" && pwd)"

echo "=== Cloud Monitoring Bootstrap: {{cookiecutter.project_name}} ==="
echo "  Project: $PROJECT"
echo ""

# --- Notification channels (idempotent: reuse by display name if present) ---
CHANNEL_IDS=()

_find_or_create_channel() {
  local display_name="$1"
  shift
  local existing
  existing="$(gcloud beta monitoring channels list \
    --project="$PROJECT" \
    --filter="displayName=\"$display_name\"" \
    --format="value(name)" | head -n1)"
  if [ -n "$existing" ]; then
    echo "  Reusing existing channel: $display_name"
    echo "$existing"
    return
  fi
  gcloud beta monitoring channels create \
    --project="$PROJECT" \
    --display-name="$display_name" \
    "$@" \
    --format="value(name)"
}

if [ -n "${ALERT_EMAIL:-}" ]; then
  echo "> Configuring email notification channel..."
  CHANNEL_IDS+=("$(_find_or_create_channel "{{cookiecutter.project_name}} alerts (email)" \
    --type=email \
    --channel-labels="email_address=$ALERT_EMAIL")")
fi

if [ -n "${SLACK_CHANNEL:-}" ] && [ -n "${SLACK_BOT_TOKEN:-}" ]; then
  echo "> Configuring Slack notification channel..."
  CHANNEL_IDS+=("$(_find_or_create_channel "{{cookiecutter.project_name}} alerts (Slack)" \
    --type=slack \
    --channel-labels="channel_name=$SLACK_CHANNEL,auth_token=$SLACK_BOT_TOKEN")")
fi

if [ -z "${CHANNEL_IDS[*]:-}" ]; then
  echo "  No ALERT_EMAIL or SLACK_CHANNEL/SLACK_BOT_TOKEN set -- alert policies will be"
  echo "  created without a notification channel. Attach one later in Cloud Console"
  echo "  (Monitoring > Alerting > Edit notification channels) or re-run this script."
fi

# --- Dashboard (idempotent: reuse by display name if present) ---
echo ""
echo "> Creating dashboard..."
DASHBOARD_NAME="$(python3 -c "import json; print(json.load(open('$MONITORING_DIR/dashboard.json'))['displayName'])")"
EXISTING_DASHBOARD="$(gcloud monitoring dashboards list \
  --project="$PROJECT" \
  --filter="displayName=\"$DASHBOARD_NAME\"" \
  --format="value(name)" | head -n1)"
if [ -n "$EXISTING_DASHBOARD" ]; then
  # The Dashboards API rejects an update without the dashboard's current etag
  # ("Update Dashboard should specify a non empty etag"), and dashboard.json is a
  # checked-in template that cannot carry one. Read the live etag and inject it,
  # with the resource name, into a temp copy of the config.
  DASHBOARD_ETAG="$(gcloud monitoring dashboards describe "$EXISTING_DASHBOARD" \
    --project="$PROJECT" \
    --format="value(etag)")"
  if [ -z "$DASHBOARD_ETAG" ]; then
    echo "ERROR: could not read the etag of $EXISTING_DASHBOARD -- refusing to update," >&2
    echo "       since the API would reject it. Check your permissions on the dashboard." >&2
    exit 1
  fi
  tmp_dashboard="$(mktemp)"
  python3 -c "
import json, sys
config = json.load(open(sys.argv[1]))
config['name'] = sys.argv[2]
config['etag'] = sys.argv[3]
json.dump(config, open(sys.argv[4], 'w'))
" "$MONITORING_DIR/dashboard.json" "$EXISTING_DASHBOARD" "$DASHBOARD_ETAG" "$tmp_dashboard"
  gcloud monitoring dashboards update "$EXISTING_DASHBOARD" \
    --project="$PROJECT" \
    --config-from-file="$tmp_dashboard"
  rm -f "$tmp_dashboard"
else
  gcloud monitoring dashboards create \
    --project="$PROJECT" \
    --config-from-file="$MONITORING_DIR/dashboard.json"
fi

# --- Alert policies: inject notification channels, then create or update ---
echo ""
echo "> Creating alert policies..."
CHANNELS_JSON="$(python3 -c "import json,sys; print(json.dumps([c for c in sys.argv[1:] if c]))" "${CHANNEL_IDS[@]:-}")"

for policy_file in "$MONITORING_DIR"/alerting/*.json; do
  policy_name="$(python3 -c "import json; print(json.load(open('$policy_file'))['displayName'])")"
  tmp_policy="$(mktemp)"
  python3 -c "
import json, sys
policy = json.load(open('$policy_file'))
policy['notificationChannels'] = json.loads('$CHANNELS_JSON')
json.dump(policy, open('$tmp_policy', 'w'))
"
  existing_policy="$(gcloud monitoring policies list \
    --project="$PROJECT" \
    --filter="displayName=\"$policy_name\"" \
    --format="value(name)" | head -n1)"
  if [ -n "$existing_policy" ]; then
    gcloud monitoring policies update "$existing_policy" \
      --project="$PROJECT" \
      --policy-from-file="$tmp_policy"
  else
    gcloud monitoring policies create \
      --project="$PROJECT" \
      --policy-from-file="$tmp_policy"
  fi
  rm -f "$tmp_policy"
  echo "  $policy_name"
done

echo ""
echo "=== Monitoring setup complete ==="
echo "  Dashboard: https://console.cloud.google.com/monitoring/dashboards?project=$PROJECT"
echo "  Alerts:    https://console.cloud.google.com/monitoring/alerting/policies?project=$PROJECT"
