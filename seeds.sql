-- Vocabulary seed: the confluence, draw-on-liquidity and entry-model tags the
-- journal ships with, applied automatically when a new database is created.
-- sort_order sets the order they appear in the pickers.
--
-- Edit this file before first run to change the vocabulary, or add and reorder
-- tags later with SQL against the `tag` table -- nothing in the app hardcodes
-- these names. `family` rolls timeframe variants (5m FVG, 15m FVG, ...) into one
-- bucket so per-tag breakdowns reach a usable sample size sooner.

INSERT INTO tag (kind, name, family, sort_order, description) VALUES
  ('confluence', 'po3',               NULL,  1, NULL),
  ('confluence', 'HTF SMT',           'SMT', 2, NULL),
  ('confluence', '5m FVG',            'FVG', 3, NULL),
  ('confluence', '15m FVG',           'FVG', 4, NULL),
  ('confluence', 'LTF SMT',           'SMT', 5, NULL),
  ('confluence', '30m FVG',           'FVG', 6, NULL),
  ('confluence', '4hr FVG',           'FVG', 7, NULL),
  ('confluence', '1hr FVG',           'FVG', 8, NULL),
  ('confluence', '2hr FVG',           'FVG', 9, NULL),
  ('confluence', '10m FVG',           'FVG', 10, NULL),

  ('dol', 'HTF DOL',           NULL, 1, NULL),
  ('dol', 'ERL',               NULL, 2, NULL),
  ('dol', 'Imbalance',         NULL, 3, NULL),
  ('dol', 'LRL',               NULL, 4, NULL),
  ('dol', 'Engineered',        NULL, 5, NULL),
  ('dol', 'EQX/REQX',          NULL, 6, NULL),
  ('dol', '9:30 open H/L',     NULL, 7, NULL),
  ('dol', 'Data',              NULL, 8, 'Data release acting as the draw/target.'),
  ('dol', 'PDH/L',             NULL, 9, NULL),
  ('dol', 'Session Liquidity', NULL, 10, NULL),
  ('dol', 'PWH/L',             NULL, 11, NULL),

  ('entry', '1m IFVG',           'IFVG',         1, NULL),
  ('entry', '9:30 Judas',        NULL,           2, NULL),
  ('entry', '5m Continuation',   'Continuation', 3, NULL),
  ('entry', '30s IFVG',          'IFVG',         4, NULL),
  ('entry', 'PDI',               NULL,           5, NULL),
  ('entry', '2m IFVG',           'IFVG',         6, NULL),
  ('entry', 'Mech',              NULL,           7, NULL),
  ('entry', '15m+ Continuation', 'Continuation', 8, NULL),
  ('entry', 'CISD',              NULL,           9, NULL),
  ('entry', '3m IFVG',           'IFVG',        10, NULL);
