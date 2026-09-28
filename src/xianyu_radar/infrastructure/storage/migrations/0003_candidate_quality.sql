ALTER TABLE candidates ADD COLUMN quality_flag TEXT NOT NULL DEFAULT 'normal';
UPDATE candidates SET quality_flag='legacy_unverified';
CREATE INDEX idx_candidates_quality_score ON candidates(quality_flag, score DESC);
