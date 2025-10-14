-- OATS Agent Event Store Schema
-- Persistent event-driven architecture with PostgreSQL

-- Executions table - tracks agent execution metadata
CREATE TABLE IF NOT EXISTS agent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    max_turns INTEGER NOT NULL DEFAULT 15,
    user_id VARCHAR(255),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT valid_status CHECK (status IN ('running', 'completed', 'failed', 'paused', 'cancelled'))
);

-- Events table - stores all agent events for streaming
CREATE TABLE IF NOT EXISTS agent_events (
    id BIGSERIAL PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES agent_executions(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    success BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User feedback table - stores user interventions
CREATE TABLE IF NOT EXISTS user_feedback (
    id BIGSERIAL PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES agent_executions(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    feedback_type VARCHAR(20) NOT NULL,
    feedback_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT valid_feedback_type CHECK (feedback_type IN ('interrupt', 'input', 'approval'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_agent_events_execution_id ON agent_events(execution_id, id);
CREATE INDEX IF NOT EXISTS idx_agent_events_created_at ON agent_events(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_events_event_type ON agent_events(event_type);
CREATE INDEX IF NOT EXISTS idx_agent_executions_user_id ON agent_executions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_executions_status ON agent_executions(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_feedback_execution_turn ON user_feedback(execution_id, turn_number, processed);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at on executions
DROP TRIGGER IF EXISTS update_agent_executions_updated_at ON agent_executions;
CREATE TRIGGER update_agent_executions_updated_at
    BEFORE UPDATE ON agent_executions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to notify on new events (for LISTEN/NOTIFY pattern)
CREATE OR REPLACE FUNCTION notify_new_event()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'execution_' || NEW.execution_id::text,
        json_build_object(
            'event_id', NEW.id,
            'turn', NEW.turn_number,
            'type', NEW.event_type
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to notify listeners when new events are inserted
DROP TRIGGER IF EXISTS trigger_notify_new_event ON agent_events;
CREATE TRIGGER trigger_notify_new_event
    AFTER INSERT ON agent_events
    FOR EACH ROW
    EXECUTE FUNCTION notify_new_event();

-- Function for cleanup of old events (data retention)
CREATE OR REPLACE FUNCTION cleanup_old_events(retention_days INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM agent_events
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL
    AND execution_id IN (
        SELECT id FROM agent_executions
        WHERE status IN ('completed', 'failed', 'cancelled')
        AND completed_at < NOW() - (retention_days || ' days')::INTERVAL
    );

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- View for execution summaries (useful for analytics)
CREATE OR REPLACE VIEW execution_summaries AS
SELECT
    e.id,
    e.goal,
    e.status,
    e.user_id,
    e.created_at,
    e.completed_at,
    EXTRACT(EPOCH FROM (COALESCE(e.completed_at, NOW()) - e.created_at)) as duration_seconds,
    e.max_turns,
    COUNT(DISTINCT ev.turn_number) as turns_taken,
    COUNT(ev.id) as total_events,
    SUM(CASE WHEN ev.success = FALSE THEN 1 ELSE 0 END) as failed_events,
    COUNT(DISTINCT f.id) as feedback_count
FROM agent_executions e
LEFT JOIN agent_events ev ON e.id = ev.execution_id
LEFT JOIN user_feedback f ON e.id = f.execution_id
GROUP BY e.id, e.goal, e.status, e.user_id, e.created_at, e.completed_at, e.max_turns;

-- Grant appropriate permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE ON agent_executions TO oats_app;
-- GRANT SELECT, INSERT ON agent_events TO oats_app;
-- GRANT SELECT, INSERT, UPDATE ON user_feedback TO oats_app;
-- GRANT USAGE ON SEQUENCE agent_events_id_seq TO oats_app;
-- GRANT USAGE ON SEQUENCE user_feedback_id_seq TO oats_app;
