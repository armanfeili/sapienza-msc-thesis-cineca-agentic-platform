-- Migration: Add metrics column to agent_runs table
-- Date: 2025-11-09
-- Purpose: Store execution metrics (LLM calls, tool execution latency, etc.)

-- Add metrics column as JSONB
ALTER TABLE agent_runs 
ADD COLUMN IF NOT EXISTS metrics JSONB;

-- Add index for metrics queries
CREATE INDEX IF NOT EXISTS idx_agent_runs_metrics_gin ON agent_runs USING gin(metrics);

-- Add comment
COMMENT ON COLUMN agent_runs.metrics IS 'Execution metrics: overall_ms, llm calls, tool calls';
