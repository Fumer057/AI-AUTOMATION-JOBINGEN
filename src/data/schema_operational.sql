-- Operational Store Schema

CREATE TABLE IF NOT EXISTS generation_history (
    run_id TEXT PRIMARY KEY,
    run_date TEXT NOT NULL,
    pillar TEXT,
    topic_id TEXT,
    template_type TEXT,
    qa_score REAL,
    qa_attempts INTEGER,
    approved INTEGER DEFAULT 0,
    output_path TEXT,
    content_state_json TEXT,
    artifact_versions_json TEXT,
    error_log TEXT,
    llm_cost_usd REAL DEFAULT 0.0,
    duration_ms INTEGER,
    created_at TEXT NOT NULL,
    engagement_score REAL
);

CREATE TABLE IF NOT EXISTS llm_call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    module TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    cached INTEGER NOT NULL,
    prompt_hash TEXT,
    called_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES generation_history (run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pipeline_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES generation_history (run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS learning_insights (
    insight_id TEXT PRIMARY KEY,
    insight_type TEXT NOT NULL,
    insight_value TEXT NOT NULL,
    confidence REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engagement_scores (
    run_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    engagement_rate REAL DEFAULT 0.0,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (run_id, platform),
    FOREIGN KEY (run_id) REFERENCES generation_history (run_id) ON DELETE CASCADE
);
