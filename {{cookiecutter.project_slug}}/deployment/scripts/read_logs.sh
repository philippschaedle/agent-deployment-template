#!/usr/bin/env bash
# Stream Cloud Logging output for this agent.
# Usage: bash deployment/scripts/read_logs.sh [--since 1h] [--limit 100]
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT in .env}"
SINCE="${1:-1h}"
LIMIT="${2:-200}"

echo "Fetching logs for {{cookiecutter.project_slug}} (last $SINCE, limit $LIMIT)..."
echo ""

gcloud logging read \
  "resource.type=\"aiplatform.googleapis.com/Endpoint\"
   OR resource.type=\"ml_job\"
   OR jsonPayload.agent_name=\"root_agent\"" \
  --project="$PROJECT" \
  --freshness="$SINCE" \
  --limit="$LIMIT" \
  --format="json" \
  | python3 -c "
import json, sys
entries = json.load(sys.stdin)
for e in entries:
    ts = e.get('timestamp', '')[:19]
    severity = e.get('severity', 'INFO')[:4]
    payload = e.get('jsonPayload') or e.get('textPayload') or e.get('protoPayload') or {}
    if isinstance(payload, dict):
        msg = payload.get('message') or payload.get('msg') or payload.get('event') or json.dumps(payload)
    else:
        msg = str(payload)
    color = '\033[31m' if severity in ('ERRO','CRIT') else '\033[33m' if severity == 'WARN' else '\033[0m'
    print(f'{color}[{ts}] [{severity}] {msg}\033[0m')
"
