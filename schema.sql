-- Trading journal schema, v1.
-- Applied by journal.db.migrate() when PRAGMA user_version = 0.

-- ---------------------------------------------------------------- vocabulary

CREATE TABLE tag (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL CHECK (kind IN ('confluence','dol','entry')),
  name        TEXT NOT NULL COLLATE NOCASE,
  family      TEXT,              -- roll-up: '1hr FVG' + '30m FVG' -> 'FVG'
  color       TEXT,              -- display only; never filtered or grouped on
  description TEXT,
  is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (kind, name)
);

CREATE INDEX ix_tag_kind ON tag(kind, sort_order);

-- ------------------------------------------------------------------- import

CREATE TABLE import_batch (
  id            INTEGER PRIMARY KEY,
  source_file   TEXT NOT NULL,
  imported_at   TEXT NOT NULL DEFAULT (datetime('now')),
  mapping_json  TEXT NOT NULL,
  rows_seen     INTEGER,
  rows_inserted INTEGER,
  rows_updated  INTEGER,
  rows_skipped  INTEGER
);

-- ------------------------------------------------------------------- trades

CREATE TABLE trade (
  id          INTEGER PRIMARY KEY,
  trade_date  TEXT NOT NULL CHECK (trade_date IS date(trade_date)),
  entry_time  TEXT NOT NULL CHECK (entry_time GLOB '[0-2][0-9]:[0-5][0-9]'
                                   AND entry_time <= '23:59'),
  trade_type  TEXT NOT NULL CHECK (trade_type IN
                ('backtesting','forwardtesting','paper','evaluation','funded')),
  planned_rr  REAL NOT NULL CHECK (planned_rr > 0),
  outcome     TEXT NOT NULL CHECK (outcome IN ('win','loss','breakeven')),
  notes       TEXT,
  psyche      TEXT,
  improvement TEXT,
  external_id TEXT UNIQUE,
  import_batch_id INTEGER REFERENCES import_batch(id) ON DELETE SET NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX ix_trade_date      ON trade(trade_date, entry_time, id);
CREATE INDEX ix_trade_type_date ON trade(trade_type, trade_date);
CREATE INDEX ix_trade_created   ON trade(created_at DESC);

CREATE TRIGGER trg_trade_touch AFTER UPDATE ON trade FOR EACH ROW BEGIN
  UPDATE trade SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TABLE trade_tag (
  trade_id INTEGER NOT NULL REFERENCES trade(id) ON DELETE CASCADE,
  tag_id   INTEGER NOT NULL REFERENCES tag(id)   ON DELETE RESTRICT,
  PRIMARY KEY (trade_id, tag_id)
) WITHOUT ROWID;

CREATE INDEX ix_trade_tag_tag ON trade_tag(tag_id);

CREATE TABLE trade_screenshot (
  trade_id      INTEGER NOT NULL REFERENCES trade(id) ON DELETE CASCADE,
  timeframe     TEXT    NOT NULL CHECK (timeframe IN ('ltf','htf')),
  ordinal       INTEGER NOT NULL DEFAULT 1 CHECK (ordinal BETWEEN 1 AND 8),
  rel_path      TEXT    NOT NULL,
  original_name TEXT,
  sha256        TEXT,
  bytes         INTEGER,
  added_at      TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (trade_id, timeframe, ordinal)
) WITHOUT ROWID;

CREATE TABLE chip_color (
  dimension TEXT NOT NULL CHECK (dimension IN ('day','trade_type','outcome')),
  value     TEXT NOT NULL,
  color     TEXT NOT NULL,
  PRIMARY KEY (dimension, value)
) WITHOUT ROWID;

CREATE TABLE lookup_alias (
  kind      TEXT NOT NULL CHECK (kind IN ('confluence','dol','entry')),
  alias     TEXT NOT NULL COLLATE NOCASE,
  target_id INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  PRIMARY KEY (kind, alias)
) WITHOUT ROWID;

-- --------------------------------------------------------------- note search

CREATE VIRTUAL TABLE trade_fts USING fts5(
  notes, psyche, improvement,
  content='trade', content_rowid='id', tokenize='porter unicode61'
);

CREATE TRIGGER trg_fts_ai AFTER INSERT ON trade BEGIN
  INSERT INTO trade_fts(rowid, notes, psyche, improvement)
  VALUES (NEW.id, NEW.notes, NEW.psyche, NEW.improvement);
END;

CREATE TRIGGER trg_fts_ad AFTER DELETE ON trade BEGIN
  INSERT INTO trade_fts(trade_fts, rowid, notes, psyche, improvement)
  VALUES ('delete', OLD.id, OLD.notes, OLD.psyche, OLD.improvement);
END;

CREATE TRIGGER trg_fts_au AFTER UPDATE ON trade BEGIN
  INSERT INTO trade_fts(trade_fts, rowid, notes, psyche, improvement)
  VALUES ('delete', OLD.id, OLD.notes, OLD.psyche, OLD.improvement);
  INSERT INTO trade_fts(rowid, notes, psyche, improvement)
  VALUES (NEW.id, NEW.notes, NEW.psyche, NEW.improvement);
END;

-- -------------------------------------------------------------- derived view

-- Realized R, day of week, minutes from the 09:30 open and the trade-type
-- group are all derived here. None of them are ever stored.
-- Buckets floor toward negative infinity so pre-open entries land correctly:
-- SQLite's / truncates toward zero, which would put -3 min in bucket 0, not -5.
CREATE VIEW v_trade AS
SELECT
  b.*,
  b.min_from_open - ((b.min_from_open %  5) +  5) %  5 AS bucket_5m,
  b.min_from_open - ((b.min_from_open % 15) + 15) % 15 AS bucket_15m
FROM (
  SELECT
    t.*,
    CASE t.outcome
      WHEN 'win'  THEN t.planned_rr
      WHEN 'loss' THEN -1.0
      ELSE 0.0
    END                                                 AS r,
    CAST(strftime('%w', t.trade_date) AS INTEGER)       AS dow,
    CASE t.trade_type
      WHEN 'backtesting'    THEN 'simulated'
      WHEN 'forwardtesting' THEN 'simulated'
      WHEN 'paper'          THEN 'simulated'
      ELSE 'live'
    END                                                 AS trade_type_group,
    (CAST(substr(t.entry_time,1,2) AS INTEGER)*60
     + CAST(substr(t.entry_time,4,2) AS INTEGER)) - 570 AS min_from_open
  FROM trade t
) b;
