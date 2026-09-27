-- xianyu-radar schema v1
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watch_keywords (
    keyword TEXT PRIMARY KEY,
    exclude_patterns TEXT, -- JSON array of extra exclude substrings
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id TEXT PRIMARY KEY,
    nickname TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_scan_at TEXT,
    status TEXT NOT NULL DEFAULT 'watching', -- watching|paused|dropped
    consecutive_failures INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS seller_pool_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    source_keyword TEXT,
    source_item_id TEXT,
    reason TEXT NOT NULL DEFAULT 'discovered_via_keyword',
    joined_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_pool_seller ON seller_pool_entries(seller_id);

CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    title TEXT,
    price TEXT,
    url TEXT,
    category TEXT,
    status TEXT NOT NULL DEFAULT 'active', -- active|removed|unknown
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_price TEXT,
    last_title TEXT,
    check_count INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'seller_scan' -- discovery|seller_scan
);

CREATE INDEX IF NOT EXISTS idx_items_seller ON items(seller_id);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);

CREATE TABLE IF NOT EXISTS item_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    title TEXT,
    price TEXT,
    captured_at TEXT NOT NULL,
    scan_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_item_time
    ON item_snapshots(item_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_scan ON item_snapshots(scan_id);

CREATE TABLE IF NOT EXISTS item_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- NEW_ITEM|REMOVED_ITEM|PRICE_CHANGED|TITLE_CHANGED
    old_value TEXT,
    new_value TEXT,
    is_baseline INTEGER NOT NULL DEFAULT 0,
    detected_at TEXT NOT NULL,
    scan_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_time ON item_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_seller_time
    ON item_events(seller_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_type_time
    ON item_events(event_type, detected_at DESC);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id TEXT PRIMARY KEY,
    keyword TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    item_count INTEGER NOT NULL DEFAULT 0,
    seller_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running' -- running|ok|failed
);

CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    seller_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running', -- running|ok|failed
    error_kind TEXT, -- auth|rate_limit|empty|parse|network|None
    item_count INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_title TEXT NOT NULL UNIQUE,
    sample_item_id TEXT,
    sample_title TEXT,
    sample_price TEXT,
    sample_url TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    seller_count INTEGER NOT NULL DEFAULT 0,
    appearance_count INTEGER NOT NULL DEFAULT 0,
    score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new' -- new|watching|testing|validated|rejected
);

CREATE INDEX IF NOT EXISTS idx_candidates_seen ON candidates(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(score DESC);

CREATE TABLE IF NOT EXISTS candidate_sellers (
    candidate_id INTEGER NOT NULL REFERENCES candidates(candidate_id),
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    first_item_id TEXT,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (candidate_id, seller_id)
);
