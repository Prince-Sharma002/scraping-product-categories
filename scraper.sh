#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# OrderMonk — Bulk Keyword Scraper (Oxylabs → S3 → Brain)
# 
# Usage:
#   ./scraper.sh <keyword_file>             # scrape from a file
#   ./scraper.sh "serum" "toner"            # scrape specific keywords
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

OXYLABS_USER="prince_123_o6lXi"
OXYLABS_PASS="Albert5050prince+"
INGEST_URL="https://api.ordermonk.com/api/ingest/bulk-products"
DOMAIN="in"            # Amazon domain: in, com, co.uk, de
PAGES_PER_KEYWORD=10   # Pages to scrape per keyword (10 pages ≈ 500 products)
SLEEP_BETWEEN=2        # Seconds to wait between requests (rate limit safety)
CURL_TIMEOUT=120       # Max seconds per Oxylabs request

# Read from file if the first argument is a file, else use arguments as array
if [ $# -gt 0 ] && [ -f "$1" ]; then
  mapfile -t KEYWORDS < "$1"
elif [ $# -gt 0 ]; then
  KEYWORDS=("$@")
else
  echo "Usage: ./scraper.sh <keyword_file.txt> or ./scraper.sh \"keyword\""
  exit 1
fi

TOTAL=${#KEYWORDS[@]}
SUCCESS=0
FAILED=0
TOTAL_PRODUCTS=0
TOTAL_KEYWORDS_FOUND=0

echo "═══════════════════════════════════════════════════════════"
echo "🚀 OrderMonk Bulk Scraper — $TOTAL keywords × $PAGES_PER_KEYWORD pages"
echo "   Domain: amazon.$DOMAIN | Endpoint: $INGEST_URL"
echo "   Timeout: ${CURL_TIMEOUT}s | Sleep: ${SLEEP_BETWEEN}s between requests"
echo "═══════════════════════════════════════════════════════════"
echo ""

START_TIME=$(date +%s)

for i in "${!KEYWORDS[@]}"; do
  keyword="${KEYWORDS[$i]}"
  # Skip empty lines
  if [ -z "$keyword" ]; then continue; fi

  num=$((i + 1))
  echo "[$num/$TOTAL] 🔍 $keyword"

  # Build JSON payload safely
  PAYLOAD="{\"source\":\"amazon_search\",\"domain\":\"$DOMAIN\",\"query\":\"$keyword\",\"pages\":$PAGES_PER_KEYWORD,\"parse\":true}"

  # 1. Fetch from Oxylabs
  OXY_RESP=$(curl -s --max-time "$CURL_TIMEOUT" -X POST "https://realtime.oxylabs.io/v1/queries" \
      -u "$OXYLABS_USER:$OXYLABS_PASS" \
      -H "Content-Type: application/json" \
      -d "$PAYLOAD" 2>/dev/null) || OXY_RESP=""

  if [ -z "$OXY_RESP" ]; then
    echo "  ❌ Failed: No response from Oxylabs (timeout or connection error)"
    FAILED=$((FAILED + 1))
    continue
  fi

  # 2. Forward to OrderMonk Ingest
  RESULT=$(echo "$OXY_RESP" | curl -s --max-time 30 -X POST "$INGEST_URL" \
      -H "Content-Type: application/json" -d @- 2>/dev/null) || RESULT=""

  # Parse result (with safe defaults)
  OK=$(echo "$RESULT" | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('ok',''))" 2>/dev/null || echo "")

  if [ "$OK" = "True" ]; then
    STORED=$(echo "$RESULT" | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('stored',0))" 2>/dev/null || echo 0)
    KW=$(echo "$RESULT" | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('analysis',{}).get('nlp',{}).get('keywords_found',0))" 2>/dev/null || echo 0)
    CAT=$(echo "$RESULT" | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('analysis',{}).get('gemini',{}).get('classification','?'))" 2>/dev/null || echo "?")
    echo "  ✅ ${STORED:-0} products → S3 | ${KW:-0} keywords | Category: ${CAT:-?}"
    SUCCESS=$((SUCCESS + 1))
    TOTAL_PRODUCTS=$((TOTAL_PRODUCTS + ${STORED:-0}))
    TOTAL_KEYWORDS_FOUND=$((TOTAL_KEYWORDS_FOUND + ${KW:-0}))
  else
    ERROR=$(echo "$RESULT" | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('message','Unknown error'))" 2>/dev/null || echo "No response from Ingest API / timeout")
    echo "  ❌ Failed: $ERROR"
    # Debug: if RESULT is not empty but OK is not True, show it
    if [ -n "$RESULT" ] && [[ "$RESULT" != *"ok"* ]]; then
        echo "     Raw Ingest Response: $RESULT"
    fi
    FAILED=$((FAILED + 1))
  fi

  # Rate limit safety — sleep between requests (skip after last)
  if [ "$num" -lt "$TOTAL" ]; then
    sleep "$SLEEP_BETWEEN"
  fi
done

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
MINS=$(( ELAPSED / 60 ))
SECS=$(( ELAPSED % 60 ))

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "📊 Summary"
echo "   ✅ Success: $SUCCESS/$TOTAL keywords"
echo "   ❌ Failed:  $FAILED"
echo "   📦 Total products: $TOTAL_PRODUCTS"
echo "   🔑 Total keywords extracted: $TOTAL_KEYWORDS_FOUND"
echo "   ⏱  Time: ${MINS}m ${SECS}s"
echo "═══════════════════════════════════════════════════════════"
