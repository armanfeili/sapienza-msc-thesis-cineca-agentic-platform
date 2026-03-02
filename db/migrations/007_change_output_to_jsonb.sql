-- Migration 007: Change agent_runs.output from TEXT to JSONB
-- This allows the API to return structured output without client-side JSON parsing

-- First, wrap non-JSON text outputs in a JSON object with a "text" field
UPDATE agent_runs
SET output = jsonb_build_object('text', output)::text
WHERE output IS NOT NULL 
  AND output != ''
  AND output !~ '^\s*[\{\[]';  -- Not starting with { or [

-- Now convert the column to JSONB
ALTER TABLE agent_runs 
ALTER COLUMN output TYPE JSONB 
USING CASE 
    WHEN output IS NULL OR output = '' THEN NULL
    ELSE output::jsonb
END;

-- Add comment explaining the change
COMMENT ON COLUMN agent_runs.output IS 'Agent run output (structured data, stored as JSONB for direct access)';

-- Add GIN index for JSONB queries (improves query performance)
CREATE INDEX IF NOT EXISTS idx_agent_runs_output_gin ON agent_runs USING gin(output);

