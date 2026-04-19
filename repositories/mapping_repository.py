from db.sqlite_manager import SqliteManager


class MappingRepository:
    def __init__(self, db: SqliteManager) -> None:
        self.db = db

    def list_enabled_rules(self, platform: str) -> list[dict]:
        rows = self.db.fetch_all(
            """
            SELECT platform, match_key, detail_category, major_category
            FROM mapping_rules
            WHERE platform = ? AND enabled = 1
            ORDER BY id
            """,
            (platform,),
        )
        return [dict(row) for row in rows]
