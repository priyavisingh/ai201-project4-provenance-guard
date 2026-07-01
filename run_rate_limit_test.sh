#!/bin/bash
# Run on a freshly started server (python app.py) before any other submissions.
set -e
BASE="http://127.0.0.1:5001"

echo "=== RATE LIMIT TEST (12 rapid requests) ==="
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE/submit" \
    -H "Content-Type: application/json" \
    -d '{"text": "This is a test submission for rate limit testing purposes only.", "creator_id": "ratelimit-test"}'
done
