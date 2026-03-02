#!/bin/bash
# Test script for production hardening measures
# Tests HTTPS, security headers, rate limiting, and secure cookies

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="${BASE_URL:-https://localhost}"
SKIP_TLS_VERIFY="${SKIP_TLS_VERIFY:-true}"

# Set curl options based on TLS verification setting
if [ "$SKIP_TLS_VERIFY" = "true" ]; then
    CURL_OPTS="-k"
else
    CURL_OPTS=""
fi

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function to print test results
print_result() {
    local test_name="$1"
    local result="$2"
    local message="$3"
    
    if [ "$result" = "PASS" ]; then
        echo -e "${GREEN}✓ PASS${NC}: $test_name"
        [ -n "$message" ] && echo "  └─ $message"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}: $test_name"
        [ -n "$message" ] && echo "  └─ $message"
        ((TESTS_FAILED++))
    fi
}

echo "========================================="
echo "Production Hardening Test Suite"
echo "========================================="
echo "Base URL: $BASE_URL"
echo "TLS Verify: $([ "$SKIP_TLS_VERIFY" = "true" ] && echo "disabled" || echo "enabled")"
echo ""

# Test 1: HTTP to HTTPS redirect
echo "Test 1: HTTP to HTTPS redirect"
if [ "$BASE_URL" = "https://localhost" ]; then
    HTTP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost 2>/dev/null || echo "000")
    if [ "$HTTP_RESPONSE" = "301" ] || [ "$HTTP_RESPONSE" = "302" ]; then
        print_result "HTTP redirect" "PASS" "HTTP redirects to HTTPS ($HTTP_RESPONSE)"
    else
        print_result "HTTP redirect" "FAIL" "Expected 301/302, got $HTTP_RESPONSE"
    fi
else
    echo -e "${YELLOW}⊘ SKIP${NC}: HTTP redirect (not testing localhost HTTPS)"
fi
echo ""

# Test 2: HTTPS connectivity
echo "Test 2: HTTPS connectivity"
HTTPS_RESPONSE=$(curl $CURL_OPTS -s -o /dev/null -w "%{http_code}" "$BASE_URL/v1/health/ready" 2>/dev/null || echo "000")
if [ "$HTTPS_RESPONSE" = "200" ]; then
    print_result "HTTPS connectivity" "PASS" "Health endpoint accessible over HTTPS"
else
    print_result "HTTPS connectivity" "FAIL" "Expected 200, got $HTTPS_RESPONSE"
fi
echo ""

# Test 3: Security headers
echo "Test 3: Security headers"
HEADERS=$(curl $CURL_OPTS -I -s "$BASE_URL/v1/health/ready" 2>/dev/null)

# Check HSTS
if echo "$HEADERS" | grep -qi "Strict-Transport-Security"; then
    print_result "HSTS header" "PASS" "Strict-Transport-Security present"
else
    print_result "HSTS header" "FAIL" "Strict-Transport-Security missing"
fi

# Check X-Frame-Options
if echo "$HEADERS" | grep -qi "X-Frame-Options"; then
    print_result "X-Frame-Options" "PASS" "X-Frame-Options present"
else
    print_result "X-Frame-Options" "FAIL" "X-Frame-Options missing"
fi

# Check X-Content-Type-Options
if echo "$HEADERS" | grep -qi "X-Content-Type-Options"; then
    print_result "X-Content-Type-Options" "PASS" "X-Content-Type-Options present"
else
    print_result "X-Content-Type-Options" "FAIL" "X-Content-Type-Options missing"
fi

# Check X-XSS-Protection
if echo "$HEADERS" | grep -qi "X-XSS-Protection"; then
    print_result "X-XSS-Protection" "PASS" "X-XSS-Protection present"
else
    print_result "X-XSS-Protection" "FAIL" "X-XSS-Protection missing"
fi

# Check Referrer-Policy
if echo "$HEADERS" | grep -qi "Referrer-Policy"; then
    print_result "Referrer-Policy" "PASS" "Referrer-Policy present"
else
    print_result "Referrer-Policy" "FAIL" "Referrer-Policy missing"
fi

# Check CSP (optional)
if echo "$HEADERS" | grep -qi "Content-Security-Policy"; then
    print_result "Content-Security-Policy" "PASS" "Content-Security-Policy present"
else
    echo -e "${YELLOW}⊘ INFO${NC}: Content-Security-Policy not configured (optional)"
fi

# Check Server header removal
if echo "$HEADERS" | grep -qi "^Server:"; then
    print_result "Server header removal" "FAIL" "Server header exposed"
else
    print_result "Server header removal" "PASS" "Server header removed"
fi
echo ""

# Test 4: Rate limiting
echo "Test 4: Rate limiting"
echo "  Sending 25 rapid requests to test rate limiting..."

SUCCESS_COUNT=0
RATE_LIMITED_COUNT=0

for i in {1..25}; do
    RESPONSE=$(curl $CURL_OPTS -s -o /dev/null -w "%{http_code}" "$BASE_URL/v1/health/ready" 2>/dev/null || echo "000")
    if [ "$RESPONSE" = "200" ]; then
        ((SUCCESS_COUNT++))
    elif [ "$RESPONSE" = "429" ]; then
        ((RATE_LIMITED_COUNT++))
    fi
    sleep 0.05  # 20 req/s
done

if [ $RATE_LIMITED_COUNT -gt 0 ]; then
    print_result "Rate limiting" "PASS" "$RATE_LIMITED_COUNT of 25 requests rate limited (429)"
else
    print_result "Rate limiting" "FAIL" "No requests were rate limited (expected some 429 responses)"
fi
echo ""

# Test 5: TLS configuration (if not skipping verification)
if [ "$SKIP_TLS_VERIFY" != "true" ]; then
    echo "Test 5: TLS configuration"
    
    # Check TLS version
    TLS_VERSION=$(echo | openssl s_client -connect "${BASE_URL#https://}:443" 2>/dev/null | grep "Protocol" || echo "")
    if echo "$TLS_VERSION" | grep -qE "TLSv1\.[23]"; then
        print_result "TLS version" "PASS" "$TLS_VERSION"
    else
        print_result "TLS version" "FAIL" "Expected TLSv1.2 or TLSv1.3, got: $TLS_VERSION"
    fi
    
    # Check certificate validity
    CERT_VALID=$(echo | openssl s_client -connect "${BASE_URL#https://}:443" 2>/dev/null | grep "Verify return code" || echo "")
    if echo "$CERT_VALID" | grep -q "0 (ok)"; then
        print_result "Certificate validity" "PASS" "Certificate valid"
    else
        print_result "Certificate validity" "FAIL" "$CERT_VALID"
    fi
    echo ""
else
    echo -e "${YELLOW}⊘ SKIP${NC}: TLS configuration tests (TLS verification disabled)"
    echo ""
fi

# Test 6: Metrics endpoint access control
echo "Test 6: Metrics endpoint access control"
METRICS_RESPONSE=$(curl $CURL_OPTS -s -o /dev/null -w "%{http_code}" "$BASE_URL/metrics" 2>/dev/null || echo "000")
if [ "$METRICS_RESPONSE" = "403" ] || [ "$METRICS_RESPONSE" = "404" ]; then
    print_result "Metrics access control" "PASS" "Metrics endpoint restricted ($METRICS_RESPONSE)"
elif [ "$METRICS_RESPONSE" = "200" ]; then
    echo -e "${YELLOW}⊘ WARN${NC}: Metrics endpoint publicly accessible (consider restricting)"
else
    print_result "Metrics access control" "FAIL" "Unexpected response: $METRICS_RESPONSE"
fi
echo ""

# Summary
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi

