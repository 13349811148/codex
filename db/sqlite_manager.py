from __future__ import annotations

import sqlite3
from pathlib import Path


class SqliteManager:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        script = schema_path.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(script)
            conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._connect() as conn:
            conn.execute(sql, params)
            conn.commit()

    def fetch_one(self, sql: str, params: tuple = ()):
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()

    def fetch_all(self, sql: str, params: tuple = ()):
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()
