#!/bin/bash
# Run with server running: python app.py
set -e
BASE="http://127.0.0.1:5001"

echo "=== SUBMIT 1: High-confidence AI ==="
RESP1=$(curl -s -X POST "$BASE/submit" \
  -H "Content-Type: application/json" \
  -d @- <<'EOF'
{"text": "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment. Moreover, it is worth noting that AI plays a crucial role in shaping the multifaceted landscape of tomorrow. In conclusion, responsible innovation remains paramount.", "creator_id": "demo-user-1"}
EOF
)
echo "$RESP1" | python -m json.tool
CONTENT_ID=$(echo "$RESP1" | python -c "import sys,json; print(json.load(sys.stdin)['content_id'])")

echo ""
echo "=== SUBMIT 2: High-confidence human ==="
curl -s -X POST "$BASE/submit" \
  -H "Content-Type: application/json" \
  -d @- <<'EOF' | python -m json.tool
{"text": "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably wont go back unless someone drags me there", "creator_id": "demo-user-2"}
EOF

echo ""
echo "=== SUBMIT 3: Uncertain (formal) ==="
curl -s -X POST "$BASE/submit" \
  -H "Content-Type: application/json" \
  -d @- <<'EOF' | python -m json.tool
{"text": "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations.", "creator_id": "demo-user-3"}
EOF

echo ""
echo "=== APPEAL on submission 1 ==="
curl -s -X POST "$BASE/appeal" \
  -H "Content-Type: application/json" \
  -d "{\"content_id\": \"$CONTENT_ID\", \"creator_reasoning\": \"I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical.\"}" | python -m json.tool

echo ""
echo "=== AUDIT LOG ==="
curl -s "$BASE/log" | python -m json.tool
