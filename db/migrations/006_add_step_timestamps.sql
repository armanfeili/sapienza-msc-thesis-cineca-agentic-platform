-- Migration 006: Add step timestamps to agent_steps table
-- This enables per-step latency tracking and detailed performance analysis

-- Add timestamp columns to agent_steps
ALTER TABLE agent_steps 
ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;

-- Add indexes for timestamp-based queries
CREATE INDEX IF NOT EXISTS idx_agent_steps_timestamps 
ON agent_steps(started_at, finished_at);

-- Add index for latency calculations (WHERE both timestamps exist)
CREATE INDEX IF NOT EXISTS idx_agent_steps_duration
ON agent_steps(finished_at, started_at) 
WHERE started_at IS NOT NULL AND finished_at IS NOT NULL;

-- Add comments
COMMENT ON COLUMN agent_steps.started_at IS 'ISO timestamp when step execution started';
COMMENT ON COLUMN agent_steps.finished_at IS 'ISO timestamp when step execution finished';
