-- Migration: Add interrupt types and checkpoint support
-- Date: 2025-01-13
-- Description:
--   1. Update user_feedback to support new interrupt types (feedback, pause, stop)
--   2. Add execution_checkpoints table for pause/resume functionality

-- Step 1: Update feedback_type constraint to include new types
ALTER TABLE user_feedback
  DROP CONSTRAINT IF EXISTS valid_feedback_type;

ALTER TABLE user_feedback
  ADD CONSTRAINT valid_feedback_type
  CHECK (feedback_type IN ('feedback', 'pause', 'stop', 'interrupt', 'input', 'approval', 'user_prompt_response'));

-- Note: Keeping old types (interrupt, input, approval) for backward compatibility
-- Mapping: 'interrupt' → 'pause', but we'll handle in application layer

-- Step 2: Create execution_checkpoints table for pause/resume
CREATE TABLE IF NOT EXISTS execution_checkpoints (
  id BIGSERIAL PRIMARY KEY,
  execution_id UUID NOT NULL REFERENCES agent_executions(id) ON DELETE CASCADE,
  turn_number INTEGER NOT NULL,
  state_snapshot JSONB NOT NULL,
  transcript JSONB NOT NULL,
  resume_token VARCHAR(64) UNIQUE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  -- Only one active checkpoint per execution
  CONSTRAINT unique_active_checkpoint UNIQUE (execution_id, turn_number)
);

-- Step 3: Add index for quick resume token lookup
CREATE INDEX IF NOT EXISTS idx_checkpoints_resume_token
  ON execution_checkpoints(resume_token);

CREATE INDEX IF NOT EXISTS idx_checkpoints_execution_id
  ON execution_checkpoints(execution_id, created_at DESC);

-- Step 4: Add 'stopped' status to agent_executions (for STOP interrupt)
ALTER TABLE agent_executions
  DROP CONSTRAINT IF EXISTS valid_status;

ALTER TABLE agent_executions
  ADD CONSTRAINT valid_status
  CHECK (status IN ('running', 'completed', 'failed', 'paused', 'cancelled', 'stopped'));

-- Step 5: Function to cleanup old checkpoints (keep only latest per execution)
CREATE OR REPLACE FUNCTION cleanup_old_checkpoints(keep_count INTEGER DEFAULT 3)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM execution_checkpoints
    WHERE id NOT IN (
        SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY execution_id ORDER BY created_at DESC) as rn
            FROM execution_checkpoints
        ) t
        WHERE t.rn <= keep_count
    );

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Step 6: Add comment documentation
COMMENT ON TABLE execution_checkpoints IS 'Stores execution state snapshots for pause/resume functionality';
COMMENT ON COLUMN execution_checkpoints.state_snapshot IS 'Serialized ReActState for resume';
COMMENT ON COLUMN execution_checkpoints.transcript IS 'Full transcript history up to checkpoint';
COMMENT ON COLUMN execution_checkpoints.resume_token IS 'Unique token for resuming execution';

COMMENT ON CONSTRAINT valid_feedback_type ON user_feedback IS
  'Interrupt types: feedback (inject guidance and continue), pause (save and stop), stop (abort), or legacy types for backward compat';
