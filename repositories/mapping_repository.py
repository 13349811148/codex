from __future__ import annotations

from sqlite3 import Connection

from db.sqlite_manager import SqliteManager
from models.entities import MappingRule


class MappingRepository:
    def __init__(self, db: SqliteManager) -> None:
        self.db = db

    def ensure_schema(self) -> None:
        existing_columns = {row["name"] for row in self.db.fetch_all("PRAGMA table_info(mapping_rules)")}
        migrations = {
            "remark_norm": "ALTER TABLE mapping_rules ADD COLUMN remark_norm TEXT NOT NULL DEFAULT '[空]'",
            "biz_desc": "ALTER TABLE mapping_rules ADD COLUMN biz_desc TEXT NOT NULL DEFAULT '[空]'",
            "source_version": "ALTER TABLE mapping_rules ADD COLUMN source_version TEXT",
            "sync_time": "ALTER TABLE mapping_rules ADD COLUMN sync_time TEXT",
        }
        for column_name, sql in migrations.items():
            if column_name not in existing_columns:
                self.db.execute(sql)

        self.db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mapping_rules_platform_enabled
            ON mapping_rules(platform, enabled)
            """
        )

    def count_rules(self) -> int:
        row = self.db.fetch_one("SELECT COUNT(1) AS total FROM mapping_rules")
        return int(row["total"]) if row else 0

    def list_enabled_rules(self, platform: str | None = None) -> list[MappingRule]:
        sql = """
            SELECT platform, match_key, remark_norm, biz_desc, detail_category, major_category, enabled, COALESCE(source_version, '') AS source_version
            FROM mapping_rules
            WHERE enabled = 1
        """
        params: tuple = ()
        if platform is not None:
            sql += " AND platform = ?"
            params = (platform,)
        sql += " ORDER BY platform, id"
        rows = self.db.fetch_all(sql, params)
        return [
            MappingRule(
                platform=row["platform"],
                match_key=row["match_key"],
                remark_norm=row["remark_norm"],
                biz_desc=row["biz_desc"],
                detail_category=row["detail_category"],
                major_category=row["major_category"],
                source_version=row["source_version"],
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def replace_all_rules(self, rules: list[MappingRule], source_version: str) -> None:
        def operation(conn: Connection) -> None:
            conn.execute("DELETE FROM mapping_rules")
            conn.executemany(
                """
                INSERT INTO mapping_rules(
                    platform,
                    match_key,
                    remark_norm,
                    biz_desc,
                    detail_category,
                    major_category,
                    enabled,
                    source_version,
                    sync_time,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                [
                    (
                        rule.platform,
                        rule.match_key,
                        rule.remark_norm,
                        rule.biz_desc,
                        rule.detail_category,
                        rule.major_category,
                        1 if rule.enabled else 0,
                        source_version or rule.source_version,
                    )
                    for rule in rules
                ],
            )

        self.db.run_transaction(operation)
