CREATE TABLE IF NOT EXISTS runs (
    run_id UUID PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
