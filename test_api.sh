#!/bin/bash
# Pruebas de humo contra el backend en ejecución (BD vacía para el test de chat sin documentos)
API="${API:-http://127.0.0.1:5000/api}"
PASSED=0
FAILED=0

test_endpoint() {
  local name=$1 method=$2 url=$3 data=$4 expected_code=$5
  echo -n "Testing $name... "
  if [ -n "$data" ]; then
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$API$url" -H "Content-Type: application/json" -d "$data")
  else
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$API$url")
  fi
  http_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | sed '$d')
  if [ "$http_code" = "$expected_code" ]; then
    echo "✅ PASS (HTTP $http_code)"; PASSED=$((PASSED+1))
  else
    echo "❌ FAIL (Expected $expected_code, got $http_code)"; echo "Response: $body"; FAILED=$((FAILED+1))
  fi
}

echo "=== API Test Suite ==="
test_endpoint "Health Check" GET /health "" 200
test_endpoint "List Documents" GET /documents "" 200
test_endpoint "Chat empty message" POST /chat '{"message":""}' 400
test_endpoint "Delete invalid id" DELETE /documents/abc "" 400
test_endpoint "Delete missing doc" DELETE /documents/999999 "" 404
echo -n "Testing Upload without file... "
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/documents/upload")
if [ "$code" = "400" ]; then echo "✅ PASS (HTTP 400)"; PASSED=$((PASSED+1)); else echo "❌ FAIL ($code)"; FAILED=$((FAILED+1)); fi

echo ""; echo "Passed: $PASSED  Failed: $FAILED"
[ $FAILED -eq 0 ]
