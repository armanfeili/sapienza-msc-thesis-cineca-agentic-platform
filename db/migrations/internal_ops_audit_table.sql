-- Internal Operations Audit Table
-- Permanent audit trail for all internal endpoint operations

CREATE TABLE IF NOT EXISTS internal_ops_events (
    id BIGSERIAL PRIMARY KEY,
    
    -- Event identification
    correlation_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,  -- e.g., 'auto_start_override', 'preview_staged', 'db_counts'
    
    -- Actor information
    actor_sub VARCHAR(255) NOT NULL,  -- Subject from JWT (sub claim)
    actor_type VARCHAR(50),  -- 'service', 'm2m', 'system'
    
    -- Request details
    endpoint VARCHAR(255) NOT NULL,  -- Full endpoint path
    http_method VARCHAR(10) NOT NULL,  -- GET, POST, etc.
    request_params JSONB,  -- Query parameters
    request_body JSONB,  -- Request payload (if applicable)
    
    -- Response details
    http_status INTEGER NOT NULL,
    response_body JSONB,  -- Response payload (redacted if sensitive)
    
    -- Operation metadata
    operation_result VARCHAR(50) NOT NULL,  -- 'success', 'error', 'cache_hit', 'feature_unavailable'
    duration_ms INTEGER,  -- Request duration in milliseconds
    
    -- Idempotency tracking
    idempotency_key VARCHAR(255),  -- If request used idempotency
    is_idempotency_replay BOOLEAN DEFAULT FALSE,
    
    -- Cache tracking
    cache_status VARCHAR(20),  -- 'hit', 'miss', 'refresh', null
    
    -- Error details (if applicable)
    error_type VARCHAR(100),
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    
    -- Metadata
    metadata JSONB  -- Additional context, feature flags, etc.
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_internal_ops_events_correlation_id 
    ON internal_ops_events(correlation_id);

CREATE INDEX IF NOT EXISTS idx_internal_ops_events_actor_sub 
    ON internal_ops_events(actor_sub);

CREATE INDEX IF NOT EXISTS idx_internal_ops_events_event_type 
    ON internal_ops_events(event_type);

CREATE INDEX IF NOT EXISTS idx_internal_ops_events_created_at 
    ON internal_ops_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_internal_ops_events_idempotency_key 
    ON internal_ops_events(idempotency_key) 
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_internal_ops_events_result 
    ON internal_ops_events(operation_result);

-- Composite index for common audit queries
CREATE INDEX IF NOT EXISTS idx_internal_ops_events_actor_time 
    ON internal_ops_events(actor_sub, created_at DESC);

-- Comment on table
COMMENT ON TABLE internal_ops_events IS 'Audit trail for all internal operations endpoint requests';

-- Comments on key columns
COMMENT ON COLUMN internal_ops_events.correlation_id IS 'Request ID for distributed tracing';
COMMENT ON COLUMN internal_ops_events.event_type IS 'Type of internal operation performed';
COMMENT ON COLUMN internal_ops_events.actor_sub IS 'Subject claim from JWT token';
COMMENT ON COLUMN internal_ops_events.operation_result IS 'Result of operation: success, error, cache_hit, feature_unavailable';
COMMENT ON COLUMN internal_ops_events.idempotency_key IS 'Idempotency key from request header (if present)';
COMMENT ON COLUMN internal_ops_events.is_idempotency_replay IS 'True if this was served from idempotency cache';

-- Example queries for audit trail analysis:

-- Query 1: Recent operations by actor
-- SELECT event_type, operation_result, created_at, duration_ms
-- FROM internal_ops_events
-- WHERE actor_sub = 'service@clients'
-- ORDER BY created_at DESC
-- LIMIT 20;

-- Query 2: Failed operations in last hour
-- SELECT correlation_id, event_type, error_type, error_message, created_at
-- FROM internal_ops_events
-- WHERE operation_result = 'error'
--   AND created_at > NOW() - INTERVAL '1 hour'
-- ORDER BY created_at DESC;

-- Query 3: Idempotency cache hit rate
-- SELECT 
--     COUNT(*) FILTER (WHERE is_idempotency_replay = true) as cache_hits,
--     COUNT(*) FILTER (WHERE idempotency_key IS NOT NULL) as total_with_idem_key,
--     ROUND(100.0 * COUNT(*) FILTER (WHERE is_idempotency_replay = true) / 
--           NULLIF(COUNT(*) FILTER (WHERE idempotency_key IS NOT NULL), 0), 2) as hit_rate_percent
-- FROM internal_ops_events
-- WHERE created_at > NOW() - INTERVAL '24 hours';

-- Query 4: Operation performance metrics
-- SELECT 
--     event_type,
--     COUNT(*) as total_requests,
--     AVG(duration_ms) as avg_duration_ms,
--     PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms) as p50_ms,
--     PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_ms,
--     MAX(duration_ms) as max_duration_ms
-- FROM internal_ops_events
-- WHERE created_at > NOW() - INTERVAL '24 hours'
-- GROUP BY event_type
-- ORDER BY total_requests DESC;

-- Query 5: Feature availability status
-- SELECT 
--     DATE_TRUNC('hour', created_at) as hour,
--     COUNT(*) FILTER (WHERE operation_result = 'feature_unavailable') as unavailable_count,
--     COUNT(*) as total_requests
-- FROM internal_ops_events
-- WHERE event_type = 'db_counts'
--   AND created_at > NOW() - INTERVAL '7 days'
-- GROUP BY hour
-- ORDER BY hour DESC;
