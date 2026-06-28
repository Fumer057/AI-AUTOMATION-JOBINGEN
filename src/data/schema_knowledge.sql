-- Knowledge Store Schema

CREATE TABLE IF NOT EXISTS calendar_config (
    pillar TEXT PRIMARY KEY,
    target_weight REAL NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS topics_bank (
    topic_id TEXT PRIMARY KEY,
    pillar TEXT NOT NULL,
    topic_title TEXT NOT NULL,
    topic_context TEXT NOT NULL,
    suggested_template TEXT,
    used INTEGER DEFAULT 0,
    last_used TEXT,
    times_used INTEGER DEFAULT 0,
    source TEXT DEFAULT 'manual',
    active INTEGER DEFAULT 1,
    ingested_at TEXT,
    FOREIGN KEY (pillar) REFERENCES calendar_config (pillar)
);

CREATE TABLE IF NOT EXISTS jobs_sheet (
    job_id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    location TEXT NOT NULL,
    link TEXT NOT NULL,
    posted_date TEXT NOT NULL,
    featured INTEGER DEFAULT 0,
    source TEXT DEFAULT 'manual',
    active INTEGER DEFAULT 1,
    ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS testimonials (
    testimonial_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    quote TEXT NOT NULL,
    role_landed TEXT NOT NULL,
    photo_path TEXT,
    used INTEGER DEFAULT 0
);
