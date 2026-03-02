#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Cineca Agentic Platform — Health Check Script
#
# Checks:
#   1) API liveness/readiness endpoints (/livez, /readyz, /healthz)
#   2) Optional Docker container state for app, Memgraph, and Redis
#   3) Optional TCP port probes (Bolt 7687 for Memgraph, Redis 6379)
#
# Exit codes:
#   0 = all systems healthy
#   1 = one or more checks failed (hard failure)
#   2 = degraded (e.g., readiness not ready, or container stopped while API is up)
#
# Usage:
#   check_health.sh
#     [--url <base_url>] [--timeout <sec>] [--retries <N>]
#     [--app-container <name>] [--memgraph-container <name>] [--redis-container <name>]
#     [--no-docker]
#     [--probe-memgraph-port <host:port>] [--probe-redis-port <host:port>]
#     [--json] [--verbose]
#
# Examples:
#   ./check_health.sh --url http://localhost:8000 --app-container cineca-api
#   ./check_health.sh --memgraph-container memgraph --probe-memgraph-port localhost:7687
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# --- Logging helpers -----------------------------------------------------------
log()  { printf "\033[1;34m[INFO]\033[0m %s\n"  "$*" >&2; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n"  "$*" >&2; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n"  "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

# --- Usage --------------------------------------------------------------------
usage() {
  cat <<'USAGE'
Usage:
  check_health.sh
    [--url <base_url>] [--timeout <sec>] [--retries <N>]
    [--app-container <name>] [--memgraph-container <name>] [--redis-container <name>]
    [--no-docker]
    [--probe-memgraph-port <host:port>] [--probe-redis-port <host:port>]
    [--json] [--verbose] [-h|--help]

Options:
  --url <base_url>            API base URL (default: env API_BASE_URL or http://localhost:8000)
  --timeout <sec>             Curl timeout per request (default: 5)
  --retries <N>               Retry attempts for HTTP checks (default: 2)
  --app-container <name>      Docker container name for the API app (optional)
  --memgraph-container <name> Docker container name for Memgraph (optional)
  --redis-container <name>    Docker container name for Redis (optional)
  --no-docker                 Skip all Docker-based checks
  --probe-memgraph-port H:P   Also probe Memgraph TCP (e.g., localhost:7687)
  --probe-redis-port H:P      Also probe Redis TCP (e.g., localhost:6379)
  --json                      Output a JSON object with results
  --verbose                   Verbose logging
  -h, --help                  Show this help text

Exit codes:
  0 = healthy
  1 = failed
  2 = degraded

Notes:
- The API is expected to expose /livez, /readyz, and /healthz (FastAPI router).
- If jq is installed, JSON parsing is more accurate; otherwise, string matching is used.
- TCP probes require nc or bash /dev/tcp support.
USAGE
}

# --- Load .env if present ------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -f "${REPO_ROOT}/.env" ]; then
  # shellcheck disable=SC1090
  set -a; . "${REPO_ROOT}/.env"; set +a
fi

# --- Defaults ------------------------------------------------------------------
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
TIMEOUT="${TIMEOUT:-5}"
RETRIES="${RETRIES:-2}"
APP_CONTAINER="${APP_CONTAINER:-}"
MEMGRAPH_CONTAINER="${MEMGRAPH_CONTAINER:-}"
REDIS_CONTAINER="${REDIS_CONTAINER:-}"
USE_DOCKER=true
JSON_OUTPUT=false
VERBOSE=false
PROBE_MG=""
PROBE_REDIS=""

# --- Args ----------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --url)                shift; API_BASE_URL="${1:-}";;
    --timeout)            shift; TIMEOUT="${1:-}";;
    --retries)            shift; RETRIES="${1:-}";;
    --app-container)      shift; APP_CONTAINER="${1:-}";;
    --memgraph-container) shift; MEMGRAPH_CONTAINER="${1:-}";;
    --redis-container)    shift; REDIS_CONTAINER="${1:-}";;
    --no-docker)          USE_DOCKER=false;;
    --probe-memgraph-port)shift; PROBE_MG="${1:-}";;
    --probe-redis-port)   shift; PROBE_REDIS="${1:-}";;
    --json)               JSON_OUTPUT=true;;
    --verbose)            VERBOSE=true;;
    -h|--help)            usage; exit 0;;
    *) err "Unknown arg: $1"; usage; exit 1;;
  esac
  shift
done

# --- Prereqs -------------------------------------------------------------------
have curl || { err "curl is required"; exit 1; }

if $USE_DOCKER; then
  if ! have docker; then
    warn "docker not found; skipping container checks"
    USE_DOCKER=false
  fi
fi

JQ=false
if have jq; then JQ=true; fi

# --- Helpers -------------------------------------------------------------------
http_get() {
  # $1 = url
  local url="$1"
  local code
  local body
  # Fail loudly on curl errors
  if ! body="$(curl -sS --max-time "$TIMEOUT" -w "\n%{http_code}" "$url")"; then
    echo "" >&2
    echo "Curl failed for $url" >&2
    return 1
  fi
  code="$(printf "%s" "$body" | tail -n1)"
  body="$(printf "%s" "$body" | sed '$d')"
  printf "%s\n" "$code|$body"
}

tcp_probe() {
  # $1 host:port
  local hp="$1"
  local host="${hp%:*}"
  local port="${hp#*:}"
  if have nc; then
    if nc -z -w "$TIMEOUT" "$host" "$port" >/dev/null 2>&1; then
      echo "up"
    else
      echo "down"
    fi
  else
    # Fallback using bash /dev/tcp
    if (exec 3<>"/dev/tcp/$host/$port") >/dev/null 2>&1; then
      exec 3<&- 3>&-
      echo "up"
    else
      echo "down"
    fi
  fi
}

docker_state() {
  # $1 container name
  local name="$1"
  docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo "unknown"
}

# --- Checks --------------------------------------------------------------------
RESULT_API_LIVE="unknown"
RESULT_API_READY="unknown"
RESULT_API_HEALTH="unknown"
DETAIL_API_HEALTH=""

declare -i fail=0
declare -i degraded=0

# Liveness
out="$(http_get "${API_BASE_URL%/}/livez")"
code="${out%%|*}"; body="${out#*|}"
$VERBOSE && log "GET /livez -> ${code}"
if [ "$code" = "200" ]; then
  if $JQ; then
    status="$(printf "%s" "$body" | jq -r '.status // empty' || true)"
  else
    status="ok"; echo "$body" | grep -qi '"ok"' || status=""
  fi
  if [ -n "$status" ]; then
    RESULT_API_LIVE="ok"
  else
    RESULT_API_LIVE="bad"; degraded+=1
  fi
else
  RESULT_API_LIVE="down"; fail+=1
fi

# Readiness
out="$(http_get "${API_BASE_URL%/}/readyz")"
code="${out%%|*}"; body="${out#*|}"
$VERBOSE && log "GET /readyz -> ${code}"
if [ "$code" = "200" ]; then
  if $JQ; then
    status="$(printf "%s" "$body" | jq -r '.status // empty' || true)"
  else
    status="ok"; echo "$body" | grep -qi '"ok"' || status=""
  fi
  if [ -n "$status" ]; then
    RESULT_API_READY="ok"
  else
    RESULT_API_READY="not_ready"; degraded+=1
  fi
else
  RESULT_API_READY="down"; fail+=1
fi

# Health
out="$(http_get "${API_BASE_URL%/}/healthz")"
code="${out%%|*}"; body="${out#*|}"
$VERBOSE && log "GET /healthz -> ${code}"
if [ "$code" = "200" ]; then
  if $JQ; then
    RESULT_API_HEALTH="$(printf "%s" "$body" | jq -r '.status // "ok"' || echo ok)"
    DETAIL_API_HEALTH="$(printf "%s" "$body" | jq -c '.checks // {}' || echo '{}')"
  else
    echo "$body" | grep -qi '"ok"' && RESULT_API_HEALTH="ok" || RESULT_API_HEALTH="degraded"
    DETAIL_API_HEALTH="{}"
  fi
  [ "$RESULT_API_HEALTH" = "ok" ] || degraded+=1
else
  RESULT_API_HEALTH="down"; fail+=1
  DETAIL_API_HEALTH="{}"
fi

# Docker checks
APP_STATE=""
MG_STATE=""
REDIS_STATE=""
if $USE_DOCKER; then
  if [ -n "$APP_CONTAINER" ]; then
    APP_STATE="$(docker_state "$APP_CONTAINER")"
    $VERBOSE && log "App container '$APP_CONTAINER' state: $APP_STATE"
    case "$APP_STATE" in
      running) : ;;
      exited|created|paused|dead|unknown) degraded+=1 ;;
    esac
  fi
  if [ -n "$MEMGRAPH_CONTAINER" ]; then
    MG_STATE="$(docker_state "$MEMGRAPH_CONTAINER")"
    $VERBOSE && log "Memgraph container '$MEMGRAPH_CONTAINER' state: $MG_STATE"
    case "$MG_STATE" in
      running) : ;;
      *) degraded+=1 ;;
    esac
  fi
  if [ -n "$REDIS_CONTAINER" ]; then
    REDIS_STATE="$(docker_state "$REDIS_CONTAINER")"
    $VERBOSE && log "Redis container '$REDIS_CONTAINER' state: $REDIS_STATE"
    case "$REDIS_STATE" in
      running) : ;;
      *) degraded+=1 ;;
    esac
  fi
fi

# TCP Probes
MG_TCP=""
REDIS_TCP=""
if [ -n "$PROBE_MG" ]; then
  MG_TCP="$(tcp_probe "$PROBE_MG")"
  $VERBOSE && log "TCP probe Memgraph $PROBE_MG: $MG_TCP"
  [ "$MG_TCP" = "up" ] || degraded+=1
fi

if [ -n "$PROBE_REDIS" ]; then
  REDIS_TCP="$(tcp_probe "$PROBE_REDIS")"
  $VERBOSE && log "TCP probe Redis $PROBE_REDIS: $REDIS_TCP"
  [ "$REDIS_TCP" = "up" ] || degraded+=1
fi

# --- Output --------------------------------------------------------------------
if $JSON_OUTPUT; then
  # Build JSON safely (fallback if no jq)
  if $JQ; then
    jq -n \
      --arg url "$API_BASE_URL" \
      --arg live "$RESULT_API_LIVE" \
      --arg ready "$RESULT_API_READY" \
      --arg health "$RESULT_API_HEALTH" \
      --argjson checks "$DETAIL_API_HEALTH" \
      --arg appc "$APP_CONTAINER" \
      --arg appstate "$APP_STATE" \
      --arg mgc "$MEMGRAPH_CONTAINER" \
      --arg mgstate "$MG_STATE" \
      --arg redisc "$REDIS_CONTAINER" \
      --arg redisstate "$REDIS_STATE" \
      --arg mgtcp "$MG_TCP" \
      --arg redistcp "$REDIS_TCP" \
      --arg outcome "$( [ $fail -gt 0 ] && echo failed || { [ $degraded -gt 0 ] && echo degraded || echo healthy; } )" \
      '{
        api: { url: $url, live: $live, ready: $ready, health: $health, checks: $checks },
        docker: {
          app:       ( $appc   | length > 0 ? {container:$appc, state:$appstate} : null ),
          memgraph:  ( $mgc    | length > 0 ? {container:$mgc,  state:$mgstate} : null ),
          redis:     ( $redisc | length > 0 ? {container:$redisc,state:$redisstate} : null )
        },
        tcp: {
          memgraph:  ( $mgtcp    | length > 0 ? $mgtcp    : null ),
          redis:     ( $redistcp | length > 0 ? $redistcp : null )
        },
        outcome: $outcome
      }'
  else
    outcome="$( [ $fail -gt 0 ] && echo failed || { [ $degraded -gt 0 ] && echo degraded || echo healthy; } )"
    printf '{\n'
    printf '  "api": {"url":"%s","live":"%s","ready":"%s","health":"%s","checks":%s},\n' \
      "$API_BASE_URL" "$RESULT_API_LIVE" "$RESULT_API_READY" "$RESULT_API_HEALTH" "$DETAIL_API_HEALTH"
    printf '  "docker": {\n'
    printf '    "app": %s,\n'    "$( [ -n "$APP_CONTAINER" ]    && printf '{"container":"%s","state":"%s"}' "$APP_CONTAINER" "$APP_STATE"    || printf null )"
    printf ',   "memgraph": %s,\n' "$( [ -n "$MEMGRAPH_CONTAINER" ] && printf '{"container":"%s","state":"%s"}' "$MEMGRAPH_CONTAINER" "$MG_STATE" || printf null )"
    printf '    "redis": %s\n'   "$( [ -n "$REDIS_CONTAINER" ]   && printf '{"container":"%s","state":"%s"}' "$REDIS_CONTAINER" "$REDIS_STATE"  || printf null )"
    printf '  },\n'
    printf '  "tcp": {"memgraph": %s, "redis": %s},\n' \
      "$( [ -n "$MG_TCP" ]    && printf '"%s"' "$MG_TCP"    || printf null )" \
      "$( [ -n "$REDIS_TCP" ] && printf '"%s"' "$REDIS_TCP" || printf null )"
    printf '  "outcome": "%s"\n' "$outcome"
    printf '}\n'
  fi
else
  log "API:   live=$RESULT_API_LIVE ready=$RESULT_API_READY health=$RESULT_API_HEALTH"
  if $JQ && [ -n "$DETAIL_API_HEALTH" ] && [ "$DETAIL_API_HEALTH" != "{}" ]; then
    log "Checks: $(printf "%s" "$DETAIL_API_HEALTH")"
  fi
  if $USE_DOCKER; then
    [ -n "$APP_CONTAINER" ]      && log "Docker app:      $APP_CONTAINER ($APP_STATE)"
    [ -n "$MEMGRAPH_CONTAINER" ] && log "Docker memgraph: $MEMGRAPH_CONTAINER ($MG_STATE)"
    [ -n "$REDIS_CONTAINER" ]    && log "Docker redis:    $REDIS_CONTAINER ($REDIS_STATE)"
  fi
  [ -n "$PROBE_MG" ]    && log "TCP memgraph $PROBE_MG: $MG_TCP"
  [ -n "$PROBE_REDIS" ] && log "TCP redis    $PROBE_REDIS: $REDIS_TCP"

  if [ $fail -gt 0 ]; then
    err "Health check FAILED"
  elif [ $degraded -gt 0 ]; then
    warn "Health check DEGRADED"
  else
    log "Health check OK"
  fi
fi

# --- Exit code -----------------------------------------------------------------
if [ $fail -gt 0 ]; then
  exit 1
elif [ $degraded -gt 0 ]; then
  exit 2
else
  exit 0
fi
