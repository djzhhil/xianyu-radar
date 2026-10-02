CREATE TABLE candidate_sources (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL REFERENCES candidates(candidate_id),
    seller_id TEXT NOT NULL REFERENCES sellers(seller_id),
    item_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('baseline_catalog', 'new_item')),
    scan_id TEXT REFERENCES scans(id),
    title TEXT NOT NULL,
    price TEXT NOT NULL,
    url TEXT NOT NULL,
    image TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE(seller_id, item_id, source_type)
);
CREATE INDEX idx_candidate_sources_candidate ON candidate_sources(candidate_id, source_id);
