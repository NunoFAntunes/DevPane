-- DevPane index schema, v1.
--
-- ``notes`` is the source of truth for the index (a denormalized copy of the
-- markdown filesystem, kept in sync by store.index). ``notes_fts`` is an FTS5
-- virtual table fed by triggers so search stays consistent on every write.

CREATE TABLE notes (
    name        TEXT PRIMARY KEY,
    body        TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    pinned      INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1))
);

CREATE INDEX notes_updated_at_idx ON notes(updated_at DESC);

CREATE VIRTUAL TABLE notes_fts USING fts5(
    name UNINDEXED,
    body,
    content='notes',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, name, body)
    VALUES (new.rowid, new.name, new.body);
END;

CREATE TRIGGER notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, name, body)
    VALUES ('delete', old.rowid, old.name, old.body);
END;

CREATE TRIGGER notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, name, body)
    VALUES ('delete', old.rowid, old.name, old.body);
    INSERT INTO notes_fts(rowid, name, body)
    VALUES (new.rowid, new.name, new.body);
END;
