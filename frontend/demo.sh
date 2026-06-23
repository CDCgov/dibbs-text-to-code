#!/usr/bin/env bash
#
# demo.sh — run the Text-to-Code demo locally.
#
# Starts the TTC backend (FastAPI/uvicorn) and a static server for index.html,
# reading configuration from a .env file. Stop both with Ctrl+C.
#
# Usage:
#   ./demo.sh                 # reads ./.env
#   ./demo.sh path/to/envfile
#
# Required (in the env file or your shell):
#   OPENSEARCH_ENDPOINT_URL   https://<domain-endpoint>
#   AWS credentials permitted on the OpenSearch domain (env vars / AWS_PROFILE / SSO)
# See .env.example for the full list.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="${1:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  echo "▸ Loading environment from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "▸ No $ENV_FILE found; using the current shell environment."
  echo "  (copy .env.example to .env and fill it in)"
fi

# Defaults
: "${OPENSEARCH_INDEX:=ttc-index}"
: "${AWS_REGION:=us-east-2}"
: "${BACKEND_PORT:=8080}"
: "${FRONTEND_PORT:=8000}"
export OPENSEARCH_INDEX AWS_REGION

if [[ -z "${OPENSEARCH_ENDPOINT_URL:-}" ]]; then
  echo "✗ OPENSEARCH_ENDPOINT_URL is not set. Add it to $ENV_FILE (see .env.example)." >&2
  exit 1
fi
export OPENSEARCH_ENDPOINT_URL

if [[ "$BACKEND_PORT" != "8080" ]]; then
  echo "! BACKEND_PORT is $BACKEND_PORT, but the frontend targets 8080."
  echo "  Update API_BASE in app.js to match, or the page won't reach the backend."
fi

pids=()
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "▸ Shutting down…"
  if [[ ${#pids[@]} -gt 0 ]]; then
    for pid in "${pids[@]}"; do
      kill "$pid" 2>/dev/null || true
    done
  fi
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "▸ Starting TTC backend on http://127.0.0.1:${BACKEND_PORT}"
echo "  (the first request waits ~10–30s while the retriever/reranker models load)"
uv run uvicorn text_to_code_lambda.local_server:app --host 127.0.0.1 --port "$BACKEND_PORT" &
pids+=($!)

echo "▸ Serving index.html on http://127.0.0.1:${FRONTEND_PORT}"
python3 -m http.server "$FRONTEND_PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
pids+=($!)

echo
echo "  Open the demo:  http://127.0.0.1:${FRONTEND_PORT}/index.html"
echo "  Press Ctrl+C to stop both servers."
echo

wait
