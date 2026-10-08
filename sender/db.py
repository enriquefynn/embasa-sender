import os
import sqlite3
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY,
    cpf        TEXT NOT NULL UNIQUE,
    password   TEXT NOT NULL,
    email      TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sent_bills (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    matricula  TEXT NOT NULL,
    referencia TEXT NOT NULL,
    due_date   TEXT,
    amount     TEXT,
    email      TEXT NOT NULL,
    sent_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, matricula, referencia)
);
"""


def connect(path: str) -> sqlite3.Connection:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_user(conn, cpf: str, password: str, email: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO users (cpf, password, email) VALUES (?, ?, ?) "
            "ON CONFLICT(cpf) DO UPDATE SET password = excluded.password, "
            "email = excluded.email, active = 1",
            (cpf, password, email),
        )


def remove_user(conn, cpf: str) -> bool:
    with conn:
        return conn.execute("DELETE FROM users WHERE cpf = ?", (cpf,)).rowcount > 0


def set_active(conn, cpf: str, active: bool) -> bool:
    with conn:
        cur = conn.execute("UPDATE users SET active = ? WHERE cpf = ?", (int(active), cpf))
        return cur.rowcount > 0


def list_users(conn, only_active: bool = False, cpf: Optional[str] = None):
    query, args = "SELECT * FROM users WHERE 1 = 1", []
    if only_active:
        query += " AND active = 1"
    if cpf:
        query += " AND cpf = ?"
        args.append(cpf)
    return conn.execute(query + " ORDER BY id", args).fetchall()


def is_sent(conn, user_id: int, matricula: str, referencia: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sent_bills WHERE user_id = ? AND matricula = ? AND referencia = ?",
        (user_id, matricula, referencia),
    ).fetchone()
    return row is not None


def mark_sent(conn, user_id: int, matricula: str, referencia: str, due_date, amount, email) -> None:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent_bills (user_id, matricula, referencia, due_date, amount, email) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, matricula, referencia, due_date, amount, email),
        )


def list_sent(conn, limit: int = 50):
    return conn.execute(
        "SELECT s.*, u.cpf FROM sent_bills s JOIN users u ON u.id = s.user_id "
        "ORDER BY s.sent_at DESC, s.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
