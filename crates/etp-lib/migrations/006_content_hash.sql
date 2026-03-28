-- Store BLAKE3 content hash for move tracking and deduplication detection.
-- Computed during metadata scan, used by reconcile_moves to match files
-- without re-reading them.
ALTER TABLE files ADD COLUMN content_hash TEXT;
