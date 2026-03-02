"""
Redis Lua Scripts for Job Store

Atomic operations implemented as Lua scripts for strict consistency.
"""

# Atomic job cancellation with CAS (Compare-And-Set) semantics
CANCEL_JOB_SCRIPT = """
-- Cancel job atomically (CAS pattern)
-- KEYS[1] = job:{id} (job HASH key)
-- ARGV[1] = current timestamp (ISO 8601)
-- ARGV[2] = result JSON ({"cancelled": true})
-- Returns: "cancelled" if transitioned, "already_terminal" if already finished/failed/cancelled, "not_found" if missing

local job_key = KEYS[1]

-- Check if job exists
if redis.call('EXISTS', job_key) == 0 then
    return "not_found"
end

-- Get current status
local current_status = redis.call('HGET', job_key, 'status')

-- Only cancel if queued or running
if current_status == 'queued' or current_status == 'running' then
    -- Update status and result atomically
    redis.call('HSET', job_key, 'status', 'cancelled')
    redis.call('HSET', job_key, 'updated_at', ARGV[1])
    redis.call('HSET', job_key, 'result', ARGV[2])
    return "cancelled"
else
    -- Already terminal (finished, failed, cancelled)
    return "already_terminal"
end
"""

# Atomic job status update with transition validation
UPDATE_STATUS_SCRIPT = """
-- Update job status with optional state machine validation
-- KEYS[1] = job:{id} (job HASH key)
-- KEYS[2] = old_status ZSET key (jobs:status:{old_status})
-- KEYS[3] = new_status ZSET key (jobs:status:{new_status})
-- ARGV[1] = new status value
-- ARGV[2] = updated_at timestamp
-- ARGV[3] = result JSON (optional, may be empty string)
-- ARGV[4] = error string (optional, may be empty string)
-- ARGV[5] = score (created_at epoch ms for ZSET)
-- ARGV[6] = TTL seconds (for terminal states)
-- Returns: "ok" if updated, "not_found" if job missing

local job_key = KEYS[1]
local old_status_key = KEYS[2]
local new_status_key = KEYS[3]

-- Check if job exists
if redis.call('EXISTS', job_key) == 0 then
    return "not_found"
end

-- Get current status
local current_status = redis.call('HGET', job_key, 'status')
local job_id = redis.call('HGET', job_key, 'id')

-- Update HASH fields
redis.call('HSET', job_key, 'status', ARGV[1])
redis.call('HSET', job_key, 'updated_at', ARGV[2])

if ARGV[3] ~= '' then
    redis.call('HSET', job_key, 'result', ARGV[3])
end

if ARGV[4] ~= '' then
    redis.call('HSET', job_key, 'error', ARGV[4])
end

-- Update ZSET indexes if status changed
if current_status ~= ARGV[1] then
    local score = tonumber(ARGV[5])

    -- Remove from old status index
    if old_status_key ~= '' then
        redis.call('ZREM', old_status_key, job_id)
    end

    -- Add to new status index
    if new_status_key ~= '' then
        redis.call('ZADD', new_status_key, score, job_id)

        -- Set TTL on new index if provided
        if ARGV[6] ~= '' and tonumber(ARGV[6]) > 0 then
            redis.call('EXPIRE', new_status_key, tonumber(ARGV[6]))
        end
    end
end

-- Set TTL on job HASH if terminal and TTL provided
local terminal_statuses = {finished=true, failed=true, cancelled=true}
if terminal_statuses[ARGV[1]] and ARGV[6] ~= '' and tonumber(ARGV[6]) > 0 then
    redis.call('EXPIRE', job_key, tonumber(ARGV[6]))
end

return "ok"
"""

# Cleanup orphaned ZSET members
CLEANUP_ORPHANS_SCRIPT = """
-- Clean orphaned members from ZSET indexes
-- KEYS[1] = ZSET index key (e.g., jobs:all, jobs:owner:*, jobs:status:*)
-- ARGV[1] = batch size (number of members to check per call)
-- Returns: number of orphaned members removed

local index_key = KEYS[1]
local batch_size = tonumber(ARGV[1])
local removed_count = 0

-- Get all members (or first N if batch size specified)
local members = redis.call('ZRANGE', index_key, 0, batch_size - 1)

for _, job_id in ipairs(members) do
    local job_key = 'job:' .. job_id

    -- Check if job HASH exists
    if redis.call('EXISTS', job_key) == 0 then
        -- Orphaned: remove from index
        redis.call('ZREM', index_key, job_id)
        removed_count = removed_count + 1
    end
end

return removed_count
"""

# Batch delete job with all related keys
DELETE_JOB_SCRIPT = """
-- Delete job and all related keys atomically
-- KEYS[1] = job:{id} (job HASH key)
-- ARGV[1] = job_id
-- ARGV[2] = owner
-- ARGV[3] = status
-- Returns: "ok" if deleted, "not_found" if missing

local job_key = KEYS[1]
local job_id = ARGV[1]
local owner = ARGV[2]
local status = ARGV[3]

-- Check if job exists
if redis.call('EXISTS', job_key) == 0 then
    return "not_found"
end

-- Delete job HASH
redis.call('DEL', job_key)

-- Remove from all indexes
redis.call('ZREM', 'jobs:all', job_id)
redis.call('ZREM', 'jobs:owner:' .. owner, job_id)
redis.call('ZREM', 'jobs:status:' .. status, job_id)

-- Delete events and counter
redis.call('DEL', 'job:' .. job_id .. ':events')
redis.call('DEL', 'job:' .. job_id .. ':event_seq')

return "ok"
"""

# Idempotency check-and-set
IDEMPOTENCY_CAS_SCRIPT = """
-- Atomically check idempotency key and set if missing
-- KEYS[1] = idempotency key
-- ARGV[1] = job_id to store
-- ARGV[2] = TTL seconds
-- Returns: existing job_id if key exists, "set" if newly created

local idem_key = KEYS[1]

-- Check if key exists
local existing_job_id = redis.call('GET', idem_key)

if existing_job_id then
    -- Key exists: return existing job_id (replay scenario)
    return existing_job_id
else
    -- Key doesn't exist: set it with TTL
    redis.call('SETEX', idem_key, tonumber(ARGV[2]), ARGV[1])
    return "set"
end
"""
