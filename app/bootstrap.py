from dataclasses import dataclass

from db.sqlite_manager import SqliteManager
from repositories.config_repository import ConfigRepository
from repositories.mapping_meta_repository import MappingMetaRepository
from repositories.mapping_repository import MappingRepository
from repositories.run_log_repository import RunLogRepository
from services.classify_service import ClassifyService
from services.mapping_editor_service import MappingEditorService
from services.mapping_runtime_service import MappingRuntimeService
from services.run_report_service import RunReportService
from services.wps_auth_service import WpsOAuthService
from services.wps_mapping_sync_service import WpsMappingSyncService
from services.wps_openapi_client import WpsOpenApiClient
from ui.main_window import MainWindow
from utils.paths import get_database_path

DEFAULT_WPS_CONFIG = {
    "wps_share_url": "https://www.kdocs.cn/l/ceP77RuNMY5a",
    "wps_file_id": "513431252713",
    "wps_sheet_name": "正式映射",
}


@dataclass
class AppServices:
    db: SqliteManager
    config_repo: ConfigRepository
    mapping_repo: MappingRepository
    mapping_meta_repo: MappingMetaRepository
    mapping_runtime_service: MappingRuntimeService
    mapping_editor_service: MappingEditorService
    classify_service: ClassifyService
    run_log_repo: RunLogRepository
    run_service: RunReportService
    wps_auth_service: WpsOAuthService
    wps_openapi_client: WpsOpenApiClient
    wps_mapping_sync_service: WpsMappingSyncService


def seed_default_wps_config(config_repo: ConfigRepository) -> None:
    for key, value in DEFAULT_WPS_CONFIG.items():
        if not config_repo.get(key, "").strip():
            config_repo.set(key, value)


def build_app_services() -> AppServices:
    db = SqliteManager(get_database_path())
    db.initialize()

    config_repo = ConfigRepository(db)
    seed_default_wps_config(config_repo)
    mapping_repo = MappingRepository(db)
    mapping_meta_repo = MappingMetaRepository(db)
    mapping_runtime_service = MappingRuntimeService(mapping_repo, mapping_meta_repo)
    mapping_runtime_service.ensure_seeded()
    mapping_editor_service = MappingEditorService(mapping_repo, mapping_meta_repo, mapping_runtime_service)
    classify_service = ClassifyService(mapping_runtime_service)
    run_log_repo = RunLogRepository(db)
    run_service = RunReportService(
        config_repo=config_repo,
        run_log_repo=run_log_repo,
        classify_service=classify_service,
    )
    wps_auth_service = WpsOAuthService(config_repo)
    wps_openapi_client = WpsOpenApiClient(wps_auth_service)
    wps_mapping_sync_service = WpsMappingSyncService(
        config_repo=config_repo,
        mapping_repository=mapping_repo,
        mapping_meta_repository=mapping_meta_repo,
        mapping_runtime_service=mapping_runtime_service,
        auth_service=wps_auth_service,
        openapi_client=wps_openapi_client,
    )

    return AppServices(
        db=db,
        config_repo=config_repo,
        mapping_repo=mapping_repo,
        mapping_meta_repo=mapping_meta_repo,
        mapping_runtime_service=mapping_runtime_service,
        mapping_editor_service=mapping_editor_service,
        classify_service=classify_service,
        run_log_repo=run_log_repo,
        run_service=run_service,
        wps_auth_service=wps_auth_service,
        wps_openapi_client=wps_openapi_client,
        wps_mapping_sync_service=wps_mapping_sync_service,
    )


def bootstrap() -> MainWindow:
    services = build_app_services()
    return MainWindow(
        run_service=services.run_service,
        config_repo=services.config_repo,
        mapping_editor_service=services.mapping_editor_service,
        mapping_meta_repo=services.mapping_meta_repo,
        wps_sync_service=services.wps_mapping_sync_service,
    )
