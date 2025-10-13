-- OATS Agent Event-Driven Architecture Database Schema
-- PostgreSQL 13+ required for gen_random_uuid()

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Core execution tracking
CREATE TABLE agent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal TEXT NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('running', 'paused', 'completed', 'failed')),
    max_turns INTEGER DEFAULT 15,
    user_id VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Event stream (append-only log)
CREATE TABLE agent_events (
    id BIGSERIAL PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES agent_executions(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    success BOOLEAN, -- NULL for non-outcome events
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User feedback queue
CREATE TABLE user_feedback (
    id BIGSERIAL PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES agent_executions(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    feedback_type VARCHAR(20) NOT NULL CHECK (feedback_type IN ('interrupt', 'input', 'approval')),
    feedback_data JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_execution_events ON agent_events(execution_id, id);
CREATE INDEX idx_execution_events_turn ON agent_events(execution_id, turn_number);
CREATE INDEX idx_events_type ON agent_events(event_type);
CREATE INDEX idx_events_created_at ON agent_events(created_at);
CREATE INDEX idx_feedback_unprocessed ON user_feedback(execution_id, processed, created_at);
CREATE INDEX idx_feedback_turn ON user_feedback(execution_id, turn_number);

-- Update trigger for agent_executions
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_agent_executions_updated_at 
    BEFORE UPDATE ON agent_executions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Sample data for testing (optional)
-- INSERT INTO agent_executions (goal, status) VALUES 
-- ('Test execution', 'completed');

-- Grant permissions (adjust as needed for your environment)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO oats_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO oats_user;
