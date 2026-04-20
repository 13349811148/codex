from __future__ import annotations

from db.sqlite_manager import SqliteManager


class MappingMetaRepository:
    def __init__(self, db: SqliteManager) -> None:
        self.db = db

    def get(self, key: str, default: str = "") -> str:
        row = self.db.fetch_one("SELECT value FROM mapping_meta WHERE key = ?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            """
            INSERT INTO mapping_meta(key, value, updated_at)
            VALUES(?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )

    def set_many(self, values: dict[str, str]) -> None:
        for key, value in values.items():
            self.set(key, value)
