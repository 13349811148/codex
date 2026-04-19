from db.sqlite_manager import SqliteManager


class RunLogRepository:
    def __init__(self, db: SqliteManager) -> None:
        self.db = db

    def add_run(
        self,
        input_dir: str,
        file_count: int,
        success_count: int,
        failed_count: int,
        export_path: str,
        status: str,
        message: str,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO run_logs(run_time, input_dir, file_count, success_count, failed_count, export_path, status, message)
            VALUES(CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
            """,
            (input_dir, file_count, success_count, failed_count, export_path, status, message),
        )
