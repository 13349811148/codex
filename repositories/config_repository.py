from db.sqlite_manager import SqliteManager


class ConfigRepository:
    def __init__(self, db: SqliteManager) -> None:
        self.db = db

    def get(self, key: str, default: str = "") -> str:
        row = self.db.fetch_one("SELECT value FROM app_config WHERE key = ?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            """
            INSERT INTO app_config(key, value, updated_at)
            VALUES(?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
