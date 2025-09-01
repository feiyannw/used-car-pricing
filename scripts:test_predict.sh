#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://used-car-bqml-295289023086-295289023086.us-central1.run.app}"

echo "== Health =="
curl -sS "$BASE_URL/health" | jq .

echo "== BQ Test =="
curl -sS "$BASE_URL/bq_test" | jq .

echo "== Predict =="
curl -sS -H "Content-Type: application/json" -X POST -d @sample_input.json \
  "$BASE_URL/predict" | jq .
