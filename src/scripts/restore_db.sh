#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Cineca Agentic Platform — Database Restore Script
#
# Restores a backup bundle (.tgz) created by scripts/backup_db.sh.
# Supports restoring Memgraph (required) and optionally copying a Redis RDB
# into a Redis container for manual/server-assisted reload.
#
# Usage:
#   restore_db.sh <backup.tgz>
#                  [--container <memgraph_container> | --local]
#                  [--force-hot]
#                  [--restore-redis --redis-container <name> --redis-dir </data> [--restart-redis]]
#                  [--no-verify]
#
# Environment (can also be set via .env at repo root):
#   MEMGRAPH_CONTAINER   : Docker container name for Memgraph (if restoring into Docker)
#   MEMGRAPH_DATA_DIR    : Local Memgraph data dir (default /var/lib/memgraph)
#   MEMGRAPH_CONF_DIR    : Local Memgraph conf dir (default /etc/memgraph)
#   BACKUP_OUTPUT_DIR    : Unused here; kept for parity
#
# Notes:
#  - For Docker restore, this script uses `docker cp` to copy restored files
#    into the container (works when running or stopped). To avoid corruption,
#    we RECOMMEND restoring while the container is STOPPED, unless --force-hot
#    is explicitly set.
#  - For local restore, root privileges are typically required to write to
#    /var/lib and /etc. This script will fail if insufficient permissions.
#  - Redis restore requires an RDB file in the bundle. This script can copy the
#    file into a Redis container directory you specify, but it WILL NOT issue
#    DEBUG/CONFIG commands on your server (those are environment-specific).
#    After copying, you should restart Redis to load the RDB, or handle it per
#    your ops standards.
# ------------------------------------------------------------------------------

set -Eeuo pipefail

# --- Helpers ------------------------------------------------------------------

log()  { printf "\033[1;34m[INFO]\033[0m %s\n"  "$*" >&2; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n"  "$*" >&2; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n"  "$*" >&2; }
die()  { err "$*"; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

abspath() {
  local p="$1"
  if [ -d "$p" ]; then (cd "$p" && pwd); else
    local d; d="$(dirname "$p")"; local f; f="$(basename "$p")"
    (cd "$d" 2>/dev/null && printf "%s/%s" "$(pwd)" "$f")
  fi
}

print_usage() {
  cat <<'USAGE'
Usage:
  restore_db.sh <backup.tgz>
                [--container <memgraph_container> | --local]
                [--force-hot]
                [--restore-redis --redis-container <name> --redis-dir </data> [--restart-redis]]
                [--no-verify]
                [-h|--help]

Options:
  <backup.tgz>                Path to a backup archive produced by backup_db.sh
  -c, --container <name>      Memgraph Docker container to restore into
      --local                 Restore to local filesystem (MEMGRAPH_DATA_DIR, MEMGRAPH_CONF_DIR)
      --force-hot             Proceed even if Memgraph/Redis containers are RUNNING
      --restore-redis         Attempt Redis RDB copy into a Redis container
      --redis-container <n>   Redis Docker container name
      --redis-dir </path>     Directory inside Redis container for dump.rdb (e.g., /data)
      --restart-redis         Restart the Redis container after copying
      --no-verify             Skip checksum verification of the bundle
  -h, --help                  Show this help

Environment:
  MEMGRAPH_CONTAINER   Docker container name for Memgraph
  MEMGRAPH_DATA_DIR    Local Memgraph data dir (default /var/lib/memgraph)
  MEMGRAPH_CONF_DIR    Local Memgraph conf dir (default /etc/memgraph)

Examples:
  # Restore Memgraph into a stopped container:
  restore_db.sh backups/cineca-backup-20240101T000000Z.tgz --container memgraph

  # Restore Memgraph locally (requires root):
  sudo restore_db.sh backups/cineca-backup-...Z.tgz --local

  # Also copy Redis RDB into container and restart it:
  restore_db.sh backups/cineca-backup-...Z.tgz \
    --container memgraph \
    --restore-redis --redis-container redis --redis-dir /data --restart-redis
USAGE
}

# --- Load .env if present -----------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -f "${REPO_ROOT}/.env" ]; then
  log "Loading environment from ${REPO_ROOT}/.env"
  # shellcheck disable=SC1090
  set -a; . "${REPO_ROOT}/.env"; set +a
fi

# --- Defaults -----------------------------------------------------------------

MEMGRAPH_CONTAINER="${MEMGRAPH_CONTAINER:-}"
MEMGRAPH_DATA_DIR="${MEMGRAPH_DATA_DIR:-/var/lib/memgraph}"
MEMGRAPH_CONF_DIR="${MEMGRAPH_CONF_DIR:-/etc/memgraph}"

DOCKER_MEMGRAPH=""
LOCAL_RESTORE=""
FORCE_HOT=false
VERIFY=true

DO_REDIS=false
REDIS_CONTAINER=""
REDIS_DIR=""
REDIS_RESTART=false

ARCHIVE=""

# --- Args ---------------------------------------------------------------------

[ $# -gt 0 ] || { print_usage; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    -c|--container)
      shift; MEMGRAPH_CONTAINER="${1:-}"; [ -n "$MEMGRAPH_CONTAINER" ] || die "Missing value for --container"
      DOCKER_MEMGRAPH="yes"
      ;;
    --local)
      LOCAL_RESTORE="yes"
      ;;
    --force-hot)
      FORCE_HOT=true
      ;;
    --restore-redis)
      DO_REDIS=true
      ;;
    --redis-container)
      shift; REDIS_CONTAINER="${1:-}"; [ -n "$REDIS_CONTAINER" ] || die "Missing value for --redis-container"
      ;;
    --redis-dir)
      shift; REDIS_DIR="${1:-}"; [ -n "$REDIS_DIR" ] || die "Missing value for --redis-dir"
      ;;
    --restart-redis)
      REDIS_RESTART=true
      ;;
    --no-verify)
      VERIFY=false
      ;;
    -h|--help)
      print_usage; exit 0
      ;;
    -*)
      die "Unknown option: $1 (use --help)"
      ;;
    *)
      if [ -z "$ARCHIVE" ]; then ARCHIVE="$1"; else die "Unexpected positional argument: $1"; fi
      ;;
  esac
  shift
done

[ -n "$ARCHIVE" ] || die "Backup archive path is required."
[ -f "$ARCHIVE" ] || die "Backup archive not found: $ARCHIVE"

if [ -n "$DOCKER_MEMGRAPH" ] && [ -n "$LOCAL_RESTORE" ]; then
  die "Choose either --container or --local for Memgraph restore, not both."
fi
if [ -z "$DOCKER_MEMGRAPH" ] && [ -z "$LOCAL_RESTORE" ]; then
  # default to container if env provided, otherwise local
  if [ -n "$MEMGRAPH_CONTAINER" ]; then
    DOCKER_MEMGRAPH="yes"
  else
    LOCAL_RESTORE="yes"
  fi
fi

# --- Workdir & extract --------------------------------------------------------

umask 077
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/cineca-restore.XXXXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

ARCHIVE_ABS="$(abspath "$ARCHIVE")"
log "Using working directory: $WORKDIR"
log "Extracting archive: $ARCHIVE_ABS"
tar -xzf "$ARCHIVE_ABS" -C "$WORKDIR"

# Expect files: memgraph.tar.gz, manifest.json, checksums.sha256, (optional) redis_dump.rdb
MEMGRAPH_TAR="${WORKDIR}/memgraph.tar.gz"
MANIFEST_JSON="${WORKDIR}/manifest.json"
CHECKSUMS="${WORKDIR}/checksums.sha256"
REDIS_RDB="${WORKDIR}/redis_dump.rdb"

[ -f "$MEMGRAPH_TAR" ] || die "memgraph.tar.gz missing in the backup bundle."
[ -f "$MANIFEST_JSON" ] || warn "manifest.json missing in the bundle."
[ -f "$CHECKSUMS" ] || warn "checksums.sha256 missing in the bundle (verification skipped)."

# --- Verify checksums ---------------------------------------------------------

if $VERIFY && [ -f "$CHECKSUMS" ]; then
  log "Verifying checksums..."
  if have sha256sum; then
    ( cd "$WORKDIR" && sha256sum -c checksums.sha256 )
  elif have shasum; then
    ( cd "$WORKDIR" && shasum -a 256 -c checksums.sha256 )
  else
    warn "No sha256sum/shasum available; skipping verification."
  fi
else
  log "Checksum verification disabled."
fi

# --- Restore Memgraph ---------------------------------------------------------

restore_memgraph_container() {
  local container="$1"
  local running="false"
  if have docker; then
    running="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || echo false)"
  else
    die "docker is required for --container restore."
  fi

  if [ "$running" = "true" ] && ! $FORCE_HOT; then
    die "Container '$container' is RUNNING. Stop it first or pass --force-hot to proceed at your own risk."
  fi

  # Extract memgraph tar to temp and docker cp into container
  local mg_extract="${WORKDIR}/mg_extract"
  mkdir -p "$mg_extract"
  log "Unpacking memgraph.tar.gz -> $mg_extract"
  tar -xzf "$MEMGRAPH_TAR" -C "$mg_extract"

  # Copy back the two directories if present
  if [ -d "${mg_extract}/var/lib/memgraph" ]; then
    log "Copying var/lib/memgraph into container:$container"
    docker cp "${mg_extract}/var/lib/memgraph/." "${container}:/var/lib/memgraph"
  else
    warn "var/lib/memgraph not found in bundle."
  fi

  if [ -d "${mg_extract}/etc/memgraph" ]; then
    log "Copying etc/memgraph into container:$container"
    docker cp "${mg_extract}/etc/memgraph/." "${container}:/etc/memgraph"
  else
    warn "etc/memgraph not found in bundle."
  fi

  log "Memgraph restore into container '$container' completed."
}

restore_memgraph_local() {
  # Requires root typically
  [ -w "$MEMGRAPH_DATA_DIR" ] || warn "MEMGRAPH_DATA_DIR not writable: $MEMGRAPH_DATA_DIR (you may need sudo)"
  [ -w "$MEMGRAPH_CONF_DIR" ] || warn "MEMGRAPH_CONF_DIR not writable: $MEMGRAPH_CONF_DIR (you may need sudo)"

  local mg_extract="${WORKDIR}/mg_extract"
  mkdir -p "$mg_extract"
  log "Unpacking memgraph.tar.gz -> $mg_extract"
  tar -xzf "$MEMGRAPH_TAR" -C "$mg_extract"

  if [ -d "${mg_extract}/var/lib/memgraph" ]; then
    log "Restoring data -> $MEMGRAPH_DATA_DIR"
    mkdir -p "$MEMGRAPH_DATA_DIR"
    # cp -a to preserve perms/times
    cp -a "${mg_extract}/var/lib/memgraph/." "$MEMGRAPH_DATA_DIR/"
  else
    warn "var/lib/memgraph not found in bundle."
  fi

  if [ -d "${mg_extract}/etc/memgraph" ]; then
    log "Restoring config -> $MEMGRAPH_CONF_DIR"
    mkdir -p "$MEMGRAPH_CONF_DIR"
    cp -a "${mg_extract}/etc/memgraph/." "$MEMGRAPH_CONF_DIR/"
  else
    warn "etc/memgraph not found in bundle."
  fi

  log "Memgraph local restore completed."
}

if [ -n "$DOCKER_MEMGRAPH" ]; then
  [ -n "$MEMGRAPH_CONTAINER" ] || die "Missing Memgraph container name (use --container or MEMGRAPH_CONTAINER env)."
  log "Restoring Memgraph into Docker container: $MEMGRAPH_CONTAINER"
  restore_memgraph_container "$MEMGRAPH_CONTAINER"
else
  log "Restoring Memgraph to local filesystem: data=$MEMGRAPH_DATA_DIR, conf=$MEMGRAPH_CONF_DIR"
  restore_memgraph_local
fi

# --- Restore Redis (optional copy of RDB) -------------------------------------

if $DO_REDIS; then
  if [ ! -f "$REDIS_RDB" ]; then
    warn "Redis RDB (redis_dump.rdb) not found in bundle; skipping Redis restore."
  else
    [ -n "$REDIS_CONTAINER" ] || die "--restore-redis requires --redis-container <name>"
    [ -n "$REDIS_DIR" ] || die "--restore-redis requires --redis-dir </path> (e.g., /data)"

    have docker || die "docker is required to copy RDB into Redis container."

    local redis_running
    redis_running="$(docker inspect -f '{{.State.Running}}' "$REDIS_CONTAINER" 2>/dev/null || echo false)"
    if [ "$redis_running" = "true" ] && ! $FORCE_HOT; then
      warn "Redis container '$REDIS_CONTAINER' is RUNNING."
      warn "Copying an RDB while Redis is live may not be applied until restart."
    fi

    # Copy file to a temp path, then move into target dir
    log "Copying redis_dump.rdb into container '$REDIS_CONTAINER' ($REDIS_DIR/dump.rdb)"
    docker cp "$REDIS_RDB" "${REDIS_CONTAINER}:/tmp/restore_dump.rdb"
    docker exec "$REDIS_CONTAINER" sh -lc "mkdir -p '$REDIS_DIR' && mv -f /tmp/restore_dump.rdb '$REDIS_DIR/dump.rdb' && ls -l '$REDIS_DIR/dump.rdb'"

    if $REDIS_RESTART; then
      log "Restarting Redis container: $REDIS_CONTAINER"
      docker restart "$REDIS_CONTAINER" >/dev/null
      log "Redis container restarted."
    else
      warn "Redis RDB copied. To load it, restart the Redis container or follow your environment's procedure."
    fi
  fi
else
  log "Redis restore not requested. (Use --restore-redis to enable if RDB is present.)"
fi

log "Restore complete."
