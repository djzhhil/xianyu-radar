ALTER TABLE discovery_items ADD COLUMN pooled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE discovery_items ADD COLUMN pool_entry_id INTEGER;
