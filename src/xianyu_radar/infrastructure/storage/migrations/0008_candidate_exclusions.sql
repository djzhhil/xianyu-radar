ALTER TABLE sellers ADD COLUMN candidate_exclude_patterns TEXT NOT NULL DEFAULT '[]';
CREATE TABLE candidate_scan_decisions (
    scan_id TEXT NOT NULL REFERENCES scans(id),
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('baseline', 'excluded', 'candidate')),
    matched_patterns TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY(scan_id, item_id)
);
