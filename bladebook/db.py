"""
bladebook/db.py — SQLite system of record for a knife collection.

Three tables: models (a manufacturer configuration — family/model/generation/
size/blade shape), knives (one physical, individually tagged knife, each
tied to a model), and events (a knife's history — acquired, photographed,
sold, etc). Photo slot assignment happens later, at editor time — photo
files themselves are keyed by tag on disk, independent of this schema.
crk_sku lives on knives, not models, since it turned out to be
per-configuration rather than per-model.
"""

import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
  id INTEGER PRIMARY KEY,
  family TEXT NOT NULL,
  model TEXT,
  generation TEXT,
  size TEXT,
  blade_shape TEXT,
  knife_type TEXT NOT NULL DEFAULT 'folder',
  production_start INTEGER, production_end INTEGER,
  blade_length_mm REAL, blade_thickness_mm REAL, weight_g REAL,
  notes TEXT,
  UNIQUE(family, model, generation, size, blade_shape)
);
CREATE TABLE IF NOT EXISTS knives (
  id INTEGER PRIMARY KEY,
  tag TEXT UNIQUE NOT NULL,
  model_id INTEGER NOT NULL REFERENCES models(id),
  edition_number TEXT, special_edition TEXT, crk_sku TEXT,
  born_on TEXT, born_on_precision TEXT NOT NULL DEFAULT 'day',
  born_on_source TEXT NOT NULL DEFAULT 'card',
  hand TEXT NOT NULL DEFAULT 'right',
  steel TEXT, hardness_note TEXT,
  damascus_smith TEXT, damascus_pattern TEXT,
  handle_treatment TEXT, graphic_name TEXT,
  inlay_material TEXT, inlay_note TEXT,
  surface_finish TEXT, hardware_note TEXT, box_upc TEXT,
  condition INTEGER, condition_note TEXT,
  factory_edge_intact INTEGER, modifications TEXT,
  has_box INTEGER, has_card INTEGER, has_papers INTEGER, has_pouch INTEGER,
  has_lanyard INTEGER, has_spare_hardware INTEGER,
  box_type TEXT, box_condition TEXT,
  sale_status TEXT NOT NULL DEFAULT 'keeping',
  asking_price REAL, price_paid REAL,
  acquired_date TEXT, acquired_from TEXT, location TEXT,
  notes_public TEXT, notes_private TEXT,
  hero_photo TEXT,
  created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  knife_id INTEGER NOT NULL REFERENCES knives(id),
  date TEXT NOT NULL, type TEXT NOT NULL,
  detail TEXT, amount REAL, counterparty TEXT, document_id INTEGER,
  public_visible INTEGER NOT NULL DEFAULT 0
);
"""


def _path():
    return os.path.join(os.environ.get('BLADEBOOK_DATA_DIR', os.path.join(os.getcwd(), 'data')),
                        'bladebook.db')


def connect():
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    con = sqlite3.connect(_path())
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    con.executescript(SCHEMA)
    return con


def _now():
    return datetime.now(timezone.utc).isoformat()


def upsert_model(con, family, model=None, generation=None, size=None,
                 blade_shape=None, knife_type='folder', **extra):
    row = con.execute(
        'SELECT id FROM models WHERE family IS ? AND model IS ? AND '
        'generation IS ? AND size IS ? AND blade_shape IS ?',
        (family, model, generation, size, blade_shape)).fetchone()
    if row:
        return row['id']
    cols = dict(family=family, model=model, generation=generation, size=size,
                blade_shape=blade_shape, knife_type=knife_type, **extra)
    keys = ', '.join(cols)
    ph = ', '.join('?' * len(cols))
    cur = con.execute(f'INSERT INTO models ({keys}) VALUES ({ph})',
                      tuple(cols.values()))
    return cur.lastrowid


_KNIFE_COLS = {
    'model_id', 'edition_number', 'special_edition', 'crk_sku',
    'born_on', 'born_on_precision', 'born_on_source', 'hand',
    'steel', 'hardness_note', 'damascus_smith', 'damascus_pattern',
    'handle_treatment', 'graphic_name', 'inlay_material', 'inlay_note',
    'surface_finish', 'hardware_note', 'box_upc',
    'condition', 'condition_note', 'factory_edge_intact', 'modifications',
    'has_box', 'has_card', 'has_papers', 'has_pouch', 'has_lanyard',
    'has_spare_hardware', 'box_type', 'box_condition',
    'sale_status', 'asking_price', 'price_paid',
    'acquired_date', 'acquired_from', 'location',
    'notes_public', 'notes_private', 'hero_photo',
}


def upsert_knife(con, tag, **fields):
    bad = set(fields) - _KNIFE_COLS
    if bad:
        raise ValueError(f'unknown knife fields: {sorted(bad)}')
    now = _now()
    row = con.execute('SELECT id FROM knives WHERE tag = ?', (tag,)).fetchone()
    if row:
        sets = ', '.join(f'{k} = ?' for k in fields)
        con.execute(f'UPDATE knives SET {sets}, updated = ? WHERE id = ?',
                    (*fields.values(), now, row['id']))
        return row['id']
    cols = dict(tag=tag, created=now, updated=now, **fields)
    keys = ', '.join(cols)
    ph = ', '.join('?' * len(cols))
    cur = con.execute(f'INSERT INTO knives ({keys}) VALUES ({ph})',
                      tuple(cols.values()))
    return cur.lastrowid


def add_event(con, knife_id, date, type, detail=None, amount=None,
              counterparty=None, public_visible=0):
    con.execute(
        'INSERT INTO events (knife_id, date, type, detail, amount, '
        'counterparty, public_visible) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (knife_id, date, type, detail, amount, counterparty, public_visible))


def list_knives(con):
    """All knives joined with their model, private fields included
    (this feeds the AUTHED admin API only — the public export in
    bladebook/export.py is a separate, whitelisted projection)."""
    rows = con.execute(
        'SELECT k.*, m.family, m.model, m.generation, m.size, m.blade_shape, '
        'm.knife_type FROM knives k JOIN models m ON m.id = k.model_id '
        'ORDER BY k.tag').fetchall()
    return [dict(r) for r in rows]


def list_events(con, knife_id):
    rows = con.execute(
        'SELECT * FROM events WHERE knife_id = ? ORDER BY date', (knife_id,))
    return [dict(r) for r in rows]
