#!/bin/bash
# Story 26.5 — CI/CD n8n Sync
# Imports all workflow JSON files into the n8n instance via API.
# Usage: bash n8n_workflows/cicd_sync.sh

set -e

N8N_BASE="https://digitalworker.dataskate.io"
N8N_API_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkMmFmN2JlMi1hMTYwLTRlZmUtYjFhOC0wMjlmM2U3OWZmMDkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQ3NzAzfQ.lOtKLp-YEdulBGSOD62uKCPTJBHOl_-0rDy2qa79FqE"
WORKFLOW_DIR="$(dirname "$0")"

echo "=== DabbahWala n8n Workflow Sync ==="
echo "Target: $N8N_BASE"
echo ""

success=0
failed=0

for file in "$WORKFLOW_DIR"/*.json; do
    name=$(basename "$file" .json)
    echo -n "Importing $name ... "

    # Try to import via n8n API
    response=$(curl -s -o /tmp/n8n_response.json -w "%{http_code}" \
        -X POST "$N8N_BASE/api/v1/workflows" \
        -H "X-N8N-API-KEY: $N8N_API_KEY" \
        -H "Content-Type: application/json" \
        -d @"$file")

    if [ "$response" -eq 200 ] || [ "$response" -eq 201 ]; then
        echo "OK (HTTP $response)"
        ((success++)) || true
    else
        # May already exist — try update by name match
        echo "SKIP/UPDATE (HTTP $response)"
        ((failed++)) || true
    fi
done

echo ""
echo "Done: $success imported, $failed skipped/failed"
echo "Review n8n dashboard at $N8N_BASE to activate workflows."
