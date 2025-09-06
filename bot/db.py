import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Optional


def ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


@contextmanager
def connect(db_path: str):
    ensure_dir(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: str) -> None:
    with connect(db_path) as con:
        cur = con.cursor()
        cur.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
              user_id INTEGER PRIMARY KEY,
              first_name TEXT,
              last_name TEXT,
              username TEXT,
              language_code TEXT,
              is_bot INTEGER DEFAULT 0,
              last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bans (
              user_id INTEGER PRIMARY KEY,
              reason TEXT,
              active INTEGER DEFAULT 1,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS notes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              text TEXT NOT NULL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              text TEXT NOT NULL,
              done INTEGER DEFAULT 0,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              done_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reminders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              text TEXT NOT NULL,
              due_ts INTEGER NOT NULL,
              status TEXT DEFAULT 'active',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              text TEXT NOT NULL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS files (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              file_id TEXT NOT NULL,
              unique_id TEXT,
              kind TEXT,
              caption TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS relays (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              direction TEXT NOT NULL, -- 'to_admin' or 'to_user'
              admin_msg_id INTEGER,    -- message id in admin chat (for to_admin)
              peer_msg_id INTEGER,     -- original msg id in user chat
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def insert(con: sqlite3.Connection, sql: str, params: Iterable[Any]) -> int:
    cur = con.execute(sql, params)
    return int(cur.lastrowid)


def query(con: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    cur = con.execute(sql, params)
    return list(cur.fetchall())


def execute(con: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> int:
    cur = con.execute(sql, params)
    return cur.rowcount
