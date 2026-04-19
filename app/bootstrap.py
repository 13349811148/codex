from db.sqlite_manager import SqliteManager
from repositories.config_repository import ConfigRepository
from repositories.run_log_repository import RunLogRepository
from services.run_report_service import RunReportService
from ui.main_window import MainWindow
from utils.paths import get_database_path


def bootstrap() -> MainWindow:
    db = SqliteManager(get_database_path())
    db.initialize()

    config_repo = ConfigRepository(db)
    run_log_repo = RunLogRepository(db)
    run_service = RunReportService(config_repo=config_repo, run_log_repo=run_log_repo)

    return MainWindow(run_service=run_service, config_repo=config_repo)
