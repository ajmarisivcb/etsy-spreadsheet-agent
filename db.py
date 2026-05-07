"""SQLite-backed state for tracking generated spreadsheets and Etsy listings."""

import sqlite3
from contextlib import contextmanager
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS spreadsheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    niche TEXT,
    file_path TEXT NOT NULL,
    mockup_path TEXT,
    description TEXT,
    tags TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spreadsheet_id INTEGER REFERENCES spreadsheets(id),
    etsy_listing_id INTEGER UNIQUE,
    state TEXT,
    title TEXT,
    price_cents INTEGER,
    last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def insert_spreadsheet(title: str, niche: str, file_path: str,
                       mockup_path: str, description: str, tags: list[str]) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO spreadsheets (title, niche, file_path, mockup_path, description, tags) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, niche, file_path, mockup_path, description, ",".join(tags)),
        )
        return cur.lastrowid


def insert_listing(spreadsheet_id: int, etsy_listing_id: int, state: str,
                   title: str, price_cents: int) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO listings (spreadsheet_id, etsy_listing_id, state, title, price_cents) "
            "VALUES (?, ?, ?, ?, ?)",
            (spreadsheet_id, etsy_listing_id, state, title, price_cents),
        )


def list_listings() -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT l.*, s.title AS spreadsheet_title FROM listings l "
            "LEFT JOIN spreadsheets s ON s.id = l.spreadsheet_id "
            "ORDER BY l.last_synced DESC"
        ).fetchall()
        return [dict(r) for r in rows]
