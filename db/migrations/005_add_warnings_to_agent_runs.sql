-- Migration: Add warnings column to agent_runs table
-- Purpose: Store non-fatal warnings (e.g., model fallbacks, resource constraints)
-- Date: 2025-11-09

-- Add warnings column with default empty array
ALTER TABLE agent_runs 
ADD COLUMN IF NOT EXISTS warnings JSONB DEFAULT '[]'::jsonb;

-- Add comment for documentation
COMMENT ON COLUMN agent_runs.warnings IS 'Non-fatal warnings during execution (e.g., model downgrade due to RAM)';

-- Create index for filtering runs with warnings
CREATE INDEX IF NOT EXISTS idx_agent_runs_has_warnings 
ON agent_runs ((jsonb_array_length(warnings) > 0))
WHERE jsonb_array_length(warnings) > 0;
