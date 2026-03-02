#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Cineca Agentic Platform — Database Backup Script
#
# Creates a timestamped, tamper-evident backup bundle (.tgz) containing:
#   - Memgraph data/config (local filesystem or via Docker container)
#   - Optional Redis RDB dump (if REDIS_URL is set and redis-cli is available)
#   - A manifest.json with environment & metadata
#   - SHA-256 checksums for all artifacts in the bundle
#
# Usage:
#   backup_db.sh [--output <dir>] [--container <name>] [--label <text>] [--no-redis]
#
# Env (can also be set via .env at repo root):
#   MEMGRAPH_CONTAINER   : Docker container name for Memgraph (if using Docker)
#   MEMGRAPH_DATA_DIR    : Default /var/lib/memgraph
#   MEMGRAPH_CONF_DIR    : Default /etc/memgraph
#   REDIS_URL            : e.g., redis://:pass@localhost:6379/0
#   BACKUP_OUTPUT_DIR    : Default ./backups
#
# Dependencies:
#   - tar, gzip, date, awk, sed
#   - (optional) docker
#   - (optional) redis-cli (for Redis dump using --rdb)
#   - (optional) sha256sum (or shasum)
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# --- Helpers ------------------------------------------------------------------

log()  { printf "\033[1;34m[INFO]\033[0m %s\n"  "$*" >&2; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n"  "$*" >&2; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n"  "$*" >&2; }
die()  { err "$*"; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

abspath() {
  # usage: abspath <path>
  local p="$1"
  if [ -d "$p" ]; then
    (cd "$p" && pwd)
  else
    local d
    d="$(dirname "$p")"
    local f
    f="$(basename "$p")"
    (cd "$d" 2>/dev/null && printf "%s/%s" "$(pwd)" "$f")
  fi
}

sha256_file() {
  # Echo SHA-256 for a file (portable across Linux/macOS)
  if have sha256sum; then
    sha256sum "$1" | awk '{print $1}'
  elif have shasum; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "sha256-unavailable"
  fi
}

timestamp_utc() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
slugify() { echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g'; }

print_usage() {
  cat <<'USAGE'
Usage: backup_db.sh [options]

Options:
  -o, --output <dir>       Output directory for backups (default: ./backups or $BACKUP_OUTPUT_DIR)
  -c, --container <name>   Memgraph Docker container name (or set MEMGRAPH_CONTAINER)
  -l, --label <text>       Optional label to include in the backup filename
      --no-redis           Skip Redis backup even if REDIS_URL is set
  -h, --help               Show this help

Environment:
  MEMGRAPH_CONTAINER   Docker container name for Memgraph
  MEMGRAPH_DATA_DIR    Default /var/lib/memgraph
  MEMGRAPH_CONF_DIR    Default /etc/memgraph
  REDIS_URL            redis://[:pass@]host[:port][/db]
  BACKUP_OUTPUT_DIR    Default ./backups

Notes:
  - If --container (or MEMGRAPH_CONTAINER) is provided, Memgraph files are read via `docker exec`.
  - Otherwise, the script tars local paths MEMGRAPH_DATA_DIR and MEMGRAPH_CONF_DIR.
  - Redis dump requires `redis-cli` supporting `--rdb` and a valid REDIS_URL.
USAGE
}

# --- Load .env if present (from repo root) ------------------------------------

# Attempt to find repo root relative to this script: src/scripts -> repo root is ../..
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -f "${REPO_ROOT}/.env" ]; then
  log "Loading environment from ${REPO_ROOT}/.env"
  # shellcheck disable=SC1090
  set -a; . "${REPO_ROOT}/.env"; set +a
fi

# --- Defaults -----------------------------------------------------------------

OUTPUT_DIR="${BACKUP_OUTPUT_DIR:-${REPO_ROOT}/backups}"
MEMGRAPH_CONTAINER="${MEMGRAPH_CONTAINER:-}"
MEMGRAPH_DATA_DIR="${MEMGRAPH_DATA_DIR:-/var/lib/memgraph}"
MEMGRAPH_CONF_DIR="${MEMGRAPH_CONF_DIR:-/etc/memgraph}"
REDIS_URL="${REDIS_URL:-}"
DO_REDIS=true
LABEL=""

# --- Parse args ----------------------------------------------------------------

while [ $# -gt 0 ]; do
  case "$1" in
    -o|--output)
      shift; OUTPUT_DIR="${1:-}"; [ -n "$OUTPUT_DIR" ] || die "Missing value for --output"
      ;;
    -c|--container)
      shift; MEMGRAPH_CONTAINER="${1:-}"; [ -n "$MEMGRAPH_CONTAINER" ] || die "Missing value for --container"
      ;;
    -l|--label)
      shift; LABEL="$(slugify "${1:-}")"
      ;;
    --no-redis)
      DO_REDIS=false
      ;;
    -h|--help)
      print_usage; exit 0
      ;;
    *)
      die "Unknown argument: $1 (use --help)"
      ;;
  esac
  shift
done

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(abspath "$OUTPUT_DIR")"

umask 077
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/cineca-backup.XXXXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BASENAME="cineca-backup-${TS}"
[ -n "$LABEL" ] && BASENAME="${BASENAME}-${LABEL}"

log "Backup working directory: $WORKDIR"
log "Output directory         : $OUTPUT_DIR"
[ -n "$MEMGRAPH_CONTAINER" ] && log "Memgraph container        : $MEMGRAPH_CONTAINER" || log "Memgraph (local) data     : $MEMGRAPH_DATA_DIR"
[ -n "$REDIS_URL" ] && log "Redis URL                 : (set)" || log "Redis URL                 : (not set)"

# --- Back up Memgraph ----------------------------------------------------------

backup_memgraph() {
  local out="${WORKDIR}/memgraph.tar.gz"

  if [ -n "$MEMGRAPH_CONTAINER" ]; then
    have docker || die "docker is required to read from container '${MEMGRAPH_CONTAINER}'"

    log "Creating Memgraph backup (docker exec)..."
    # Try to include both data & config if present; ignore missing dirs.
    local tar_cmd="set -Eeuo pipefail;
      shopt -s nullglob 2>/dev/null || true;
      paths=();
      [ -d '${MEMGRAPH_DATA_DIR}' ] && paths+=( '${MEMGRAPH_DATA_DIR}' );
      [ -d '${MEMGRAPH_CONF_DIR}' ] && paths+=( '${MEMGRAPH_CONF_DIR}' );
      if [ \${#paths[@]} -eq 0 ]; then
        echo 'No Memgraph paths found' >&2; exit 22;
      fi
      tar -C / -czf - \"\${paths[@]#/}\" 2>/dev/null || tar -C / -czf - \"\${paths[@]#/}\""

    docker exec -i "$MEMGRAPH_CONTAINER" bash -lc "$tar_cmd" > "$out" || die "Failed to tar Memgraph data from container"
  else
    log "Creating Memgraph backup (local filesystem)..."
    local have_any=false
    local tar_args=()
    if [ -d "$MEMGRAPH_DATA_DIR" ]; then
      tar_args+=("-C" "/" "-czf" "-" "${MEMGRAPH_DATA_DIR#/}")
      have_any=true
    fi
    if [ -d "$MEMGRAPH_CONF_DIR" ]; then
      # shellcheck disable=SC2206
      tar_args=( "${tar_args[@]}" "${MEMGRAPH_CONF_DIR#/}" )
      have_any=true
    fi
    $have_any || die "No Memgraph directories found (checked ${MEMGRAPH_DATA_DIR} and ${MEMGRAPH_CONF_DIR})"
    tar "${tar_args[@]}" > "$out" || die "Failed to tar Memgraph data"
  fi

  echo "$out"
}

# --- Back up Redis (optional) --------------------------------------------------

backup_redis() {
  $DO_REDIS || { log "Skipping Redis backup (--no-redis)"; return 0; }
  [ -n "$REDIS_URL" ] || { log "Skipping Redis backup (REDIS_URL not set)"; return 0; }
  have redis-cli || { warn "redis-cli not found; skipping Redis backup"; return 0; }

  local out="${WORKDIR}/redis_dump.rdb"
  log "Creating Redis RDB dump..."
  if redis-cli -u "$REDIS_URL" --rdb "$out" >/dev/null 2>&1; then
    echo "$out"
  else
    warn "redis-cli --rdb failed; attempting BGSAVE + copy (may require permissions)"
    # Try BGSAVE + wait
    if redis-cli -u "$REDIS_URL" BGSAVE >/dev/null 2>&1; then
      # We cannot know server-side dump path reliably; skip if unknown.
      warn "BGSAVE issued but dump location unknown; skipping copy. (Use --rdb-capable redis-cli for portable dumps.)"
      return 0
    fi
    warn "Redis backup skipped."
    return 0
  fi
}

# --- Manifest & checksums ------------------------------------------------------

write_manifest() {
  local path="${WORKDIR}/manifest.json"
  local memgraph_mode
  if [ -n "$MEMGRAPH_CONTAINER" ]; then
    memgraph_mode="docker"
  else
    memgraph_mode="local"
  fi

  cat > "$path" <<JSON
{
  "app": "cineca-agentic-platform",
  "kind": "db-backup",
  "version": "1",
  "timestamp_utc": "$(timestamp_utc)",
  "memgraph": {
    "mode": "${memgraph_mode}",
    "container": "${MEMGRAPH_CONTAINER}",
    "data_dir": "${MEMGRAPH_DATA_DIR}",
    "conf_dir": "${MEMGRAPH_CONF_DIR}"
  },
  "redis": {
    "enabled": ${DO_REDIS},
    "url_present": $( [ -n "$REDIS_URL" ] && echo true || echo false )
  },
  "host": {
    "hostname": "$(hostname 2>/dev/null || echo unknown)",
    "uname": "$(uname -a 2>/dev/null | sed 's/"/\\"/g')"
  },
  "tools": {
    "docker": $(have docker && echo true || echo false),
    "redis_cli": $(have redis-cli && echo true || echo false),
    "sha256sum": $(have sha256sum && echo true || echo false),
    "shasum": $(have shasum && echo true || echo false)
  }
}
JSON
  echo "$path"
}

write_checksums() {
  local path="${WORKDIR}/checksums.sha256"
  : > "$path"
  for f in "$WORKDIR"/*; do
    [ -f "$f" ] || continue
    local name; name="$(basename "$f")"
    printf "%s  %s\n" "$(sha256_file "$f")" "$name" >> "$path"
  done
  echo "$path"
}

# --- Execute -------------------------------------------------------------------

MEMGRAPH_TAR="$(backup_memgraph)"
REDIS_RDB="$(backup_redis || true)"
MANIFEST_JSON="$(write_manifest)"
CHECKSUMS="$(write_checksums)"

ARCHIVE_PATH="${OUTPUT_DIR}/${BASENAME}.tgz"
log "Packaging bundle: ${ARCHIVE_PATH}"

# tar the WORKDIR contents into final archive
(
  cd "$WORKDIR"
  tar -czf "$ARCHIVE_PATH" ./*
)

# Post-check: print file list and sizes
log "Backup contents:"
tar -tzf "$ARCHIVE_PATH" | sed 's/^/  - /'

log "Backup complete: ${ARCHIVE_PATH}"
printf "%s\n" "$ARCHIVE_PATH"
