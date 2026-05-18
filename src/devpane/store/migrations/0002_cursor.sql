-- M6: per-note cursor position, restored across hide/show and daemon restart.
-- The column is excluded from the FTS5 content table — only ``body`` is
-- indexed for search; existing FTS triggers are unaffected.

ALTER TABLE notes ADD COLUMN cursor_offset INTEGER NOT NULL DEFAULT 0;
