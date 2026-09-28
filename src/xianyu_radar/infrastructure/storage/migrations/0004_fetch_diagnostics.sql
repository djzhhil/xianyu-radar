ALTER TABLE discovery_runs ADD COLUMN error_kind TEXT;
ALTER TABLE discovery_runs ADD COLUMN page_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE discovery_runs ADD COLUMN raw_result_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE discovery_runs ADD COLUMN unique_item_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE discovery_runs ADD COLUMN unique_seller_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE discovery_runs ADD COLUMN enriched_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE discovery_runs ADD COLUMN unresolved_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE discovery_runs ADD COLUMN unparsed_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE discovery_runs ADD COLUMN next_page INTEGER NOT NULL DEFAULT 1;
ALTER TABLE discovery_runs ADD COLUMN max_pages INTEGER NOT NULL DEFAULT 1;

CREATE TABLE discovery_pages (
    run_id TEXT NOT NULL REFERENCES discovery_runs(id),
    page_number INTEGER NOT NULL,
    raw_count INTEGER NOT NULL,
    parsed_count INTEGER NOT NULL,
    unique_count INTEGER NOT NULL,
    next_page TEXT,
    result_type TEXT NOT NULL,
    PRIMARY KEY (run_id, page_number)
);

CREATE TABLE discovery_items (
    run_id TEXT NOT NULL REFERENCES discovery_runs(id),
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    price TEXT NOT NULL,
    url TEXT NOT NULL,
    seller_nick TEXT,
    seller_id TEXT,
    resolution TEXT NOT NULL,
    error_kind TEXT,
    diagnostic TEXT NOT NULL DEFAULT '{}',
    pooled INTEGER NOT NULL DEFAULT 0,
    pool_entry_id INTEGER,
    PRIMARY KEY (run_id, item_id)
);

CREATE TABLE discovery_entries (
    run_id TEXT NOT NULL REFERENCES discovery_runs(id),
    page_number INTEGER NOT NULL,
    entry_index INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    item_ref TEXT,
    PRIMARY KEY (run_id, page_number, entry_index)
);

CREATE TABLE scan_pages (
    scan_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    total_type TEXT NOT NULL,
    total_value TEXT,
    card_count INTEGER NOT NULL,
    parsed_count INTEGER NOT NULL,
    next_field TEXT,
    next_page TEXT,
    unique_count INTEGER NOT NULL,
    PRIMARY KEY (scan_id, page_number)
);
