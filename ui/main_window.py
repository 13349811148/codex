from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGridLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.classifier import RULE_SEPARATOR
from models.dto import RunProgress, RunResult, UnmappedCandidate
from models.entities import MappingRule
from models.wps import WpsPublishResult, WpsSyncResult, WpsUpdateCheckResult
from repositories.config_repository import ConfigRepository
from repositories.mapping_meta_repository import MappingMetaRepository
from services.mapping_editor_service import MappingEditorService
from services.run_report_service import RunReportService
from services.wps_mapping_sync_service import WpsMappingSyncService
from utils.paths import build_default_export_filename


class ReportWorker(QObject):
    progress_changed = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, run_service: RunReportService, input_dir: str, output_path: str) -> None:
        super().__init__()
        self.run_service = run_service
        self.input_dir = input_dir
        self.output_path = output_path

    @Slot()
    def run(self) -> None:
        try:
            result = self.run_service.run(
                input_dir=self.input_dir,
                output_path=self.output_path,
                progress_callback=self._emit_progress,
            )
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - worker fallback
            self.failed.emit(str(exc))

    def _emit_progress(self, progress: RunProgress) -> None:
        self.progress_changed.emit(progress)


class MappingSyncWorker(QObject):
    progress_changed = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, wps_sync_service: WpsMappingSyncService, interactive_auth: bool = True) -> None:
        super().__init__()
        self.wps_sync_service = wps_sync_service
        self.interactive_auth = interactive_auth

    @Slot()
    def run(self) -> None:
        try:
            self.progress_changed.emit("正在检查 WPS 配置...")
            self.progress_changed.emit("正在拉取在线映射，请在需要时完成浏览器授权...")
            result = self.wps_sync_service.sync(interactive_auth=self.interactive_auth)
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - worker fallback
            self.failed.emit(str(exc))


class MappingCheckWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, wps_sync_service: WpsMappingSyncService, interactive_auth: bool) -> None:
        super().__init__()
        self.wps_sync_service = wps_sync_service
        self.interactive_auth = interactive_auth

    @Slot()
    def run(self) -> None:
        try:
            result = self.wps_sync_service.check_update(interactive_auth=self.interactive_auth)
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - worker fallback
            self.failed.emit(str(exc))


class MappingPublishWorker(QObject):
    progress_changed = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        wps_sync_service: WpsMappingSyncService,
        rules: list[MappingRule],
        interactive_auth: bool = True,
    ) -> None:
        super().__init__()
        self.wps_sync_service = wps_sync_service
        self.rules = rules
        self.interactive_auth = interactive_auth

    @Slot()
    def run(self) -> None:
        try:
            self.progress_changed.emit("正在准备上传本地映射...")
            result = self.wps_sync_service.publish_rules(
                self.rules,
                interactive_auth=self.interactive_auth,
                progress_callback=self.progress_changed.emit,
            )
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - worker fallback
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    MAPPING_HEADERS = ["平台", "标准化备注", "业务描述", "明细分类", "大类"]

    def __init__(
        self,
        run_service: RunReportService,
        config_repo: ConfigRepository,
        mapping_editor_service: MappingEditorService,
        mapping_meta_repo: MappingMetaRepository,
        wps_sync_service: WpsMappingSyncService,
    ) -> None:
        super().__init__()
        self.run_service = run_service
        self.config_repo = config_repo
        self.mapping_editor_service = mapping_editor_service
        self.mapping_meta_repo = mapping_meta_repo
        self.wps_sync_service = wps_sync_service

        self.report_thread: QThread | None = None
        self.report_worker: ReportWorker | None = None
        self.sync_thread: QThread | None = None
        self.sync_worker: MappingSyncWorker | None = None
        self.check_thread: QThread | None = None
        self.check_worker: MappingCheckWorker | None = None
        self.publish_thread: QThread | None = None
        self.publish_worker: MappingPublishWorker | None = None

        self.metric_labels: dict[str, QLabel] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self.page_indexes: dict[str, int] = {}
        self.mapping_dirty = False
        self._loading_mapping_table = False
        self._check_context = "manual"
        self._check_modal = False
        self._snoozed_cloud_version = ""
        self._message_candidates: dict[int, UnmappedCandidate] = {}

        self.setWindowTitle("财务统计小工具 V2.3")
        self.resize(1340, 900)
        self.setMinimumSize(1180, 760)
        self._build_ui()
        self._load_defaults()
        QTimer.singleShot(700, self._run_startup_mapping_check)

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("Root")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(12)

        surface = QFrame()
        surface.setObjectName("Surface")
        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)

        masthead = self._build_masthead()
        surface_layout.addWidget(masthead)

        body = QFrame()
        body.setObjectName("Body")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        body_layout.addWidget(sidebar)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("PageStack")
        body_layout.addWidget(self.page_stack, 1)

        self._build_report_page()
        self._build_mapping_page()
        self._build_messages_page()
        self._build_settings_page()

        surface_layout.addWidget(body, 1)
        root_layout.addWidget(surface)
        self.setCentralWidget(central)

        self._apply_styles()
        self._set_status_badge("待运行", "idle")
        self._navigate_to_page("report")

    def _build_masthead(self) -> QFrame:
        masthead = QFrame()
        masthead.setObjectName("Masthead")
        masthead.setFixedHeight(72)
        layout = QHBoxLayout(masthead)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand_panel = QFrame()
        brand_panel.setObjectName("BrandPanel")
        brand_panel.setFixedWidth(250)
        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(24, 14, 24, 14)
        brand_layout.setSpacing(0)
        brand_title = QLabel("财务统计小工具")
        brand_title.setObjectName("BrandTitle")
        brand_layout.addWidget(brand_title)
        brand_version = QLabel("V2.3")
        brand_version.setObjectName("BrandVersion")
        brand_layout.addWidget(brand_version)
        brand_layout.addStretch(1)

        top_panel = QFrame()
        top_panel.setObjectName("TopPanel")
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(18, 10, 18, 10)
        top_layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)

        self.status_badge = QLabel()
        self.status_badge.setObjectName("StatusBadge")
        toolbar.addWidget(self.status_badge, 0, Qt.AlignVCenter | Qt.AlignRight)
        top_layout.addLayout(toolbar)
        top_layout.addStretch(1)

        layout.addWidget(brand_panel)
        layout.addWidget(top_panel, 1)
        return masthead

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(24)
        side_title = QLabel("功能分区")
        side_title.setObjectName("SidebarTitle")
        layout.addWidget(side_title)
        layout.addWidget(self._create_nav_button("report", "账单统计", active=True))
        layout.addWidget(self._create_nav_button("mapping", "分类映射"))
        layout.addWidget(self._create_nav_button("messages", "异常消息"))
        layout.addWidget(self._create_nav_button("settings", "系统设置"))
        layout.addStretch()
        return sidebar

    def _build_report_page(self) -> None:
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 12, 22, 22)
        layout.setSpacing(14)

        controls = QFrame()
        controls.setObjectName("Board")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(18, 18, 18, 18)
        controls_layout.setSpacing(10)
        controls_title = QLabel("账单统计")
        controls_title.setObjectName("BoardTitle")
        controls_layout.addWidget(controls_title)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        path_tag = QLabel("数据目录")
        path_tag.setObjectName("PathTag")
        self.folder_edit = QLineEdit()
        self.folder_edit.setObjectName("FolderEdit")
        self.folder_edit.setPlaceholderText("请选择账单所在目录")
        self.folder_button = QPushButton("浏览")
        self.folder_button.setObjectName("SecondaryButton")
        self.folder_button.clicked.connect(self._choose_folder)
        self.run_button = QPushButton("一键生成报表")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.clicked.connect(self._run_report)
        path_row.addWidget(path_tag)
        path_row.addWidget(self.folder_edit, 1)
        path_row.addWidget(self.folder_button)
        path_row.addWidget(self.run_button)
        controls_layout.addLayout(path_row)
        layout.addWidget(controls)

        metrics_layout = QGridLayout()
        metrics_layout.setHorizontalSpacing(12)
        metrics_layout.setVerticalSpacing(12)
        metrics_layout.addWidget(self._create_metric_card("file_count", "0", "扫描文件数"), 0, 0)
        metrics_layout.addWidget(self._create_metric_card("success_count", "0", "成功文件数"), 0, 1)
        metrics_layout.addWidget(self._create_metric_card("warning_count", "0", "提醒数量"), 0, 2)
        metrics_layout.addWidget(self._create_metric_card("summary_count", "0", "汇总行数"), 0, 3)
        layout.addLayout(metrics_layout)

        mapping_overview = QFrame()
        mapping_overview.setObjectName("Board")
        mapping_overview_layout = QVBoxLayout(mapping_overview)
        mapping_overview_layout.setContentsMargins(18, 18, 18, 18)
        mapping_overview_layout.setSpacing(10)
        overview_title = QLabel("映射概况")
        overview_title.setObjectName("BoardTitle")
        overview_desc = QLabel("当前本地和云端映射版本状态会同步显示，详细编辑入口在“分类映射”页面。")
        overview_desc.setObjectName("BoardDesc")
        overview_desc.setWordWrap(True)
        self.mapping_overview_local_label = QLabel("本地版本：-")
        self.mapping_overview_local_label.setObjectName("DataLabel")
        self.mapping_overview_cloud_label = QLabel("云端版本：-")
        self.mapping_overview_cloud_label.setObjectName("DataLabel")
        self.mapping_overview_status_label = QLabel("映射状态：-")
        self.mapping_overview_status_label.setObjectName("DataLabel")
        mapping_overview_layout.addWidget(overview_title)
        mapping_overview_layout.addWidget(overview_desc)
        mapping_overview_layout.addWidget(self.mapping_overview_local_label)
        mapping_overview_layout.addWidget(self.mapping_overview_cloud_label)
        mapping_overview_layout.addWidget(self.mapping_overview_status_label)
        layout.addWidget(mapping_overview)

        progress_board = QFrame()
        progress_board.setObjectName("Board")
        progress_board.setMinimumHeight(170)
        progress_layout = QVBoxLayout(progress_board)
        progress_layout.setContentsMargins(20, 20, 20, 20)
        progress_layout.setSpacing(16)
        progress_head = QHBoxLayout()
        progress_text = QVBoxLayout()
        progress_text.setSpacing(6)
        progress_title = QLabel("运行进度")
        progress_title.setObjectName("BoardTitle")
        progress_text.addWidget(progress_title)
        self.progress_percent_label = QLabel("0%")
        self.progress_percent_label.setObjectName("ProgressPercent")
        progress_head.addLayout(progress_text, 1)
        progress_head.addWidget(self.progress_percent_label, 0, Qt.AlignTop)
        progress_layout.addLayout(progress_head)

        self.status_label = QLabel("状态：待执行")
        self.status_label.setObjectName("DataLabel")
        self.status_label.setWordWrap(True)
        self.progress_label = QLabel("进度：-")
        self.progress_label.setObjectName("DataLabel")
        self.progress_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addWidget(progress_board)

        export_board = QFrame()
        export_board.setObjectName("Board")
        export_layout = QVBoxLayout(export_board)
        export_layout.setContentsMargins(18, 18, 18, 18)
        export_layout.setSpacing(12)
        export_title = QLabel("导出结果")
        export_title.setObjectName("BoardTitle")
        export_desc = QLabel("集中查看本次任务的汇总结果和报表导出路径。")
        export_desc.setObjectName("BoardDesc")
        export_desc.setWordWrap(True)
        self.summary_label = QLabel("处理结果：-")
        self.summary_label.setObjectName("DataLabel")
        self.summary_label.setWordWrap(True)
        self.export_label = QLabel("导出路径：-")
        self.export_label.setObjectName("DataLabel")
        self.export_label.setWordWrap(True)
        self.export_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        export_layout.addWidget(export_title)
        export_layout.addWidget(export_desc)
        export_layout.addWidget(self.summary_label)
        export_layout.addWidget(self.export_label)
        layout.addWidget(export_board)
        layout.addStretch()

        self.page_indexes["report"] = self.page_stack.addWidget(page)

    def _build_mapping_page(self) -> None:
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)

        info_board = QFrame()
        info_board.setObjectName("Board")
        info_layout = QVBoxLayout(info_board)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setSpacing(12)

        head = QHBoxLayout()
        text_layout = QVBoxLayout()
        title = QLabel("分类映射")
        title.setObjectName("BoardTitle")
        desc = QLabel("在本地缓存中维护映射规则，保存时自动上传云端，并检查云端是否有新版本可同步。")
        desc.setObjectName("BoardDesc")
        desc.setWordWrap(True)
        text_layout.addWidget(title)
        text_layout.addWidget(desc)
        head.addLayout(text_layout, 1)
        self.mapping_check_button = QPushButton("检查更新")
        self.mapping_check_button.setObjectName("SecondaryButton")
        self.mapping_check_button.clicked.connect(self._run_manual_mapping_check)
        self.mapping_sync_button = QPushButton("手动同步映射")
        self.mapping_sync_button.setObjectName("SecondaryButton")
        self.mapping_sync_button.clicked.connect(self._sync_mapping)
        self.mapping_save_button = QPushButton("保存并上传云端")
        self.mapping_save_button.setObjectName("PrimaryButton")
        self.mapping_save_button.clicked.connect(self._save_mapping_rules)
        head.addWidget(self.mapping_check_button)
        head.addWidget(self.mapping_sync_button)
        head.addWidget(self.mapping_save_button)
        info_layout.addLayout(head)

        self.mapping_local_version_label = QLabel("本地版本：")
        self.mapping_local_version_label.setObjectName("DataLabel")
        self.mapping_cloud_version_label = QLabel("云端版本：")
        self.mapping_cloud_version_label.setObjectName("DataLabel")
        self.mapping_check_status_label = QLabel("检查状态：-")
        self.mapping_check_status_label.setObjectName("DataLabel")
        self.mapping_checked_at_label = QLabel("最近检查：-")
        self.mapping_checked_at_label.setObjectName("DataLabel")
        self.mapping_source_label = QLabel("映射来源：")
        self.mapping_source_label.setObjectName("DataLabel")
        self.mapping_source_label.setWordWrap(True)
        info_layout.addWidget(self.mapping_local_version_label)
        info_layout.addWidget(self.mapping_cloud_version_label)
        info_layout.addWidget(self.mapping_check_status_label)
        info_layout.addWidget(self.mapping_checked_at_label)
        info_layout.addWidget(self.mapping_source_label)

        self.mapping_hint_label = QLabel("正在读取映射状态。")
        self.mapping_hint_label.setObjectName("HintNeutral")
        self.mapping_hint_label.setWordWrap(True)
        info_layout.addWidget(self.mapping_hint_label)
        layout.addWidget(info_board)

        table_board = QFrame()
        table_board.setObjectName("Board")
        table_layout = QVBoxLayout(table_board)
        table_layout.setContentsMargins(18, 18, 18, 18)
        table_layout.setSpacing(12)
        table_head = QHBoxLayout()
        table_title = QLabel("本地映射规则")
        table_title.setObjectName("BoardTitle")
        table_head.addWidget(table_title)
        table_head.addStretch()
        self.mapping_add_button = QPushButton("新增")
        self.mapping_add_button.setObjectName("SecondaryButton")
        self.mapping_add_button.clicked.connect(self._add_mapping_row)
        self.mapping_delete_button = QPushButton("删除选中")
        self.mapping_delete_button.setObjectName("SecondaryButton")
        self.mapping_delete_button.clicked.connect(self._delete_selected_mapping_rows)
        table_head.addWidget(self.mapping_add_button)
        table_head.addWidget(self.mapping_delete_button)
        table_layout.addLayout(table_head)

        self.mapping_table = QTableWidget(0, len(self.MAPPING_HEADERS))
        self.mapping_table.setHorizontalHeaderLabels(self.MAPPING_HEADERS)
        self.mapping_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.mapping_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.mapping_table.setAlternatingRowColors(True)
        self.mapping_table.verticalHeader().setVisible(False)
        self.mapping_table.horizontalHeader().setStretchLastSection(True)
        for index in range(len(self.MAPPING_HEADERS) - 1):
            self.mapping_table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeToContents)
        self.mapping_table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        self.mapping_table.itemChanged.connect(self._on_mapping_item_changed)
        table_layout.addWidget(self.mapping_table)
        layout.addWidget(table_board, 1)

        self.page_indexes["mapping"] = self.page_stack.addWidget(page)

    def _build_messages_page(self) -> None:
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)

        board = QFrame()
        board.setObjectName("Board")
        board_layout = QVBoxLayout(board)
        board_layout.setContentsMargins(18, 18, 18, 18)
        board_layout.setSpacing(12)
        head = QHBoxLayout()
        text_layout = QVBoxLayout()
        title = QLabel("异常与提醒明细")
        title.setObjectName("BoardTitle")
        desc = QLabel("集中展示导入异常和未映射提醒，支持复制选中或全部消息。")
        desc.setObjectName("BoardDesc")
        desc.setWordWrap(True)
        text_layout.addWidget(title)
        text_layout.addWidget(desc)
        head.addLayout(text_layout, 1)
        self.copy_selected_button = QPushButton("复制选中")
        self.copy_selected_button.setObjectName("SecondaryButton")
        self.copy_selected_button.clicked.connect(self._copy_selected_messages)
        self.copy_all_button = QPushButton("复制全部")
        self.copy_all_button.setObjectName("SecondaryButton")
        self.copy_all_button.clicked.connect(self._copy_all_messages)
        self.add_mapping_button = QPushButton("加入映射")
        self.add_mapping_button.setObjectName("SecondaryButton")
        self.add_mapping_button.clicked.connect(self._add_selected_messages_to_mapping)
        head.addWidget(self.add_mapping_button)
        head.addWidget(self.copy_selected_button)
        head.addWidget(self.copy_all_button)
        board_layout.addLayout(head)

        self.error_table = QTableWidget(0, 3)
        self.error_table.setHorizontalHeaderLabels(["选择", "类型", "内容"])
        self.error_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.error_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.error_table.setAlternatingRowColors(True)
        self.error_table.verticalHeader().setVisible(False)
        self.error_table.horizontalHeader().setStretchLastSection(True)
        self.error_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.error_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.error_table.setColumnWidth(0, 74)
        self.error_table.setColumnWidth(1, 110)
        board_layout.addWidget(self.error_table)
        layout.addWidget(board, 1)

        self.page_indexes["messages"] = self.page_stack.addWidget(page)

    def _build_settings_page(self) -> None:
        page = QWidget()
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)

        config_board = QFrame()
        config_board.setObjectName("Board")
        config_layout = QVBoxLayout(config_board)
        config_layout.setContentsMargins(18, 18, 18, 18)
        config_layout.setSpacing(12)

        config_title = QLabel("WPS 配置")
        config_title.setObjectName("BoardTitle")
        config_desc = QLabel("首次安装会自动带入默认在线表配置，你也可以在这里直接修改分享链接、file_id、工作表名和 WPS 授权信息。")
        config_desc.setObjectName("BoardDesc")
        config_desc.setWordWrap(True)
        config_layout.addWidget(config_title)
        config_layout.addWidget(config_desc)

        config_grid = QGridLayout()
        config_grid.setHorizontalSpacing(10)
        config_grid.setVerticalSpacing(10)

        share_label = QLabel("分享链接")
        share_label.setObjectName("PathTag")
        self.wps_share_url_edit = QLineEdit()
        self.wps_share_url_edit.setObjectName("FolderEdit")
        self.wps_share_url_edit.setPlaceholderText("例如 https://www.kdocs.cn/l/xxxx")
        config_grid.addWidget(share_label, 0, 0)
        config_grid.addWidget(self.wps_share_url_edit, 0, 1, 1, 3)

        file_id_label = QLabel("file_id")
        file_id_label.setObjectName("PathTag")
        self.wps_file_id_edit = QLineEdit()
        self.wps_file_id_edit.setObjectName("FolderEdit")
        self.wps_file_id_edit.setPlaceholderText("例如 513431252713")
        config_grid.addWidget(file_id_label, 1, 0)
        config_grid.addWidget(self.wps_file_id_edit, 1, 1)

        sheet_name_label = QLabel("工作表名")
        sheet_name_label.setObjectName("PathTag")
        self.wps_sheet_name_edit = QLineEdit()
        self.wps_sheet_name_edit.setObjectName("FolderEdit")
        self.wps_sheet_name_edit.setPlaceholderText("默认 正式映射")
        config_grid.addWidget(sheet_name_label, 1, 2)
        config_grid.addWidget(self.wps_sheet_name_edit, 1, 3)

        app_id_label = QLabel("APPID")
        app_id_label.setObjectName("PathTag")
        self.wps_app_id_edit = QLineEdit()
        self.wps_app_id_edit.setObjectName("FolderEdit")
        self.wps_app_id_edit.setPlaceholderText("例如 AK2026xxxx")
        config_grid.addWidget(app_id_label, 2, 0)
        config_grid.addWidget(self.wps_app_id_edit, 2, 1)

        app_secret_label = QLabel("APP Secret")
        app_secret_label.setObjectName("PathTag")
        self.wps_app_secret_edit = QLineEdit()
        self.wps_app_secret_edit.setObjectName("FolderEdit")
        self.wps_app_secret_edit.setPlaceholderText("WPS 开放平台的 App Secret")
        self.wps_app_secret_edit.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        config_grid.addWidget(app_secret_label, 2, 2)
        config_grid.addWidget(self.wps_app_secret_edit, 2, 3)

        redirect_label = QLabel("redirect_uri")
        redirect_label.setObjectName("PathTag")
        self.wps_redirect_uri_edit = QLineEdit()
        self.wps_redirect_uri_edit.setObjectName("FolderEdit")
        self.wps_redirect_uri_edit.setPlaceholderText("例如 http://127.0.0.1:18765/callback")
        config_grid.addWidget(redirect_label, 3, 0)
        config_grid.addWidget(self.wps_redirect_uri_edit, 3, 1, 1, 3)

        config_layout.addLayout(config_grid)

        config_actions = QHBoxLayout()
        config_actions.addStretch(1)
        self.wps_config_save_button = QPushButton("保存WPS配置")
        self.wps_config_save_button.setObjectName("SecondaryButton")
        self.wps_config_save_button.clicked.connect(self._save_wps_settings)
        config_actions.addWidget(self.wps_config_save_button)
        config_layout.addLayout(config_actions)

        layout.addWidget(config_board)
        layout.addStretch()

        self.page_indexes["settings"] = self.page_stack.addWidget(page)

    def _create_chip(self, text: str, active: bool = False) -> QLabel:
        label = QLabel(text)
        label.setObjectName("ChipActive" if active else "Chip")
        return label

    def _create_nav_button(self, key: str, text: str, active: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, nav_key=key: self._navigate_to_page(nav_key))
        self.nav_buttons[key] = button
        if active:
            button.setChecked(True)
        return button

    def _create_metric_card(self, key: str, value: str, caption: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        value_label = QLabel(value)
        value_label.setObjectName("MetricValue")
        caption_label = QLabel(caption)
        caption_label.setObjectName("MetricCaption")
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        self.metric_labels[key] = value_label
        return card

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; }
            QWidget#Root { background: #f3f1ed; }
            QFrame#Surface { background: rgba(255, 253, 250, 0.92); border: 1px solid #ddd6cb; border-radius: 28px; }
            QFrame#BrandPanel { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #23453c,stop:1 #1a332d); }
            QLabel#BrandTitle { color: #fbfaf6; font-size: 24px; font-weight: 700; }
            QLabel#BrandVersion { color: rgba(251, 250, 246, 0.72); font-size: 12px; font-weight: 700; letter-spacing: 1px; margin-top: 6px; }
            QLabel#Chip, QLabel#ChipActive, QLabel#PathTag { padding: 8px 14px; border-radius: 999px; background: #fffdfa; border: 1px solid #ddd6cb; color: #736f67; }
            QLabel#ChipActive { background: #dde8e4; color: #23453c; font-weight: 700; border-color: #c8dcd5; }
            QLabel#PathTag { font-weight: 700; color: #5d564c; }
            QLineEdit#FolderEdit { min-height: 44px; padding: 0 14px; border: 1px solid #d7d0c5; border-radius: 12px; background: #fffdfa; color: #272621; }
            QLineEdit#FolderEdit:focus { border-color: #8b9e98; }
            QPushButton#PrimaryButton, QPushButton#SecondaryButton { min-height: 42px; padding: 0 18px; border-radius: 12px; font-weight: 700; }
            QPushButton#PrimaryButton { background: #23453c; color: #fffdfa; border: none; }
            QPushButton#PrimaryButton:hover { background: #1d3932; }
            QPushButton#SecondaryButton { background: #fffdfa; color: #3f3a33; border: 1px solid #d7d0c5; }
            QPushButton#SecondaryButton:hover { background: #f6f2ea; }
            QPushButton:disabled { background: #e7e1d8; color: #9a9387; border-color: #dfd8ce; }
            QFrame#Sidebar { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(247, 243, 236, 0.96),stop:1 rgba(241, 235, 226, 0.98)); border-right: 1px solid #ddd6cb; }
            QLabel#SidebarTitle { color: #6f675c; font-size: 13px; font-weight: 700; padding-left: 4px; margin-bottom: 6px; }
            QPushButton#NavButton { min-height: 96px; padding: 0 22px; text-align: left; border-radius: 22px; border: 1px solid #d8cebf; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fffdfa,stop:0.58 #f5eee4,stop:1 #ede3d5); color: #4f493f; font-size: 18px; font-weight: 700; }
            QPushButton#NavButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fffefc,stop:0.58 #f1e7da,stop:1 #e6d9c8); border-color: #cdbfae; }
            QPushButton#NavButton[active="true"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:0.4 #f8f2ea,stop:1 #e9decd); border-color: #c7b5a0; color: #1f4339; padding-left: 26px; }
            QFrame#MetricCard, QFrame#Board { background: #fffdfa; border: 1px solid #ddd6cb; border-radius: 18px; }
            QLabel#MetricValue { color: #23453c; font-size: 28px; font-weight: 700; }
            QLabel#MetricCaption { color: #736f67; font-size: 12px; }
            QLabel#BoardTitle { color: #272621; font-size: 18px; font-weight: 700; }
            QLabel#BoardDesc { color: #736f67; font-size: 13px; line-height: 1.6; }
            QLabel#ProgressPercent { color: #23453c; font-size: 34px; font-weight: 700; min-width: 92px; }
            QLabel#DataLabel { color: #403a31; font-size: 13px; line-height: 1.6; }
            QLabel#HintNeutral, QLabel#HintWarning, QLabel#HintSuccess, QLabel#HintError { padding: 12px 14px; border-radius: 12px; border: 1px solid #ddd6cb; line-height: 1.6; }
            QLabel#HintNeutral { background: #f6f2ea; color: #5d564c; border-color: #e2d7c8; }
            QLabel#HintWarning { background: #fbf2d8; color: #8a6116; border-color: #ead498; }
            QLabel#HintSuccess { background: #e1eee8; color: #23453c; border-color: #c9dfd5; }
            QLabel#HintError { background: #f4e0dd; color: #8b463e; border-color: #e9c2bc; }
            QProgressBar { min-height: 14px; max-height: 14px; border: none; border-radius: 999px; background: #ece6dc; text-align: center; }
            QProgressBar::chunk { border-radius: 999px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #b18d54,stop:1 #23453c); }
            QTableWidget { border: 1px solid #ddd6cb; border-radius: 14px; gridline-color: #ebe3d8; background: #fffdfa; alternate-background-color: #faf7f1; color: #2f2b26; selection-background-color: #e7efec; selection-color: #23453c; }
            QHeaderView::section { background: #f8f5ef; padding: 10px 12px; border: none; border-bottom: 1px solid #ddd6cb; color: #736f67; font-weight: 700; }
            QStackedWidget#PageStack { background: transparent; }
            """
        )

    def _set_nav_active(self, active_key: str) -> None:
        for key, button in self.nav_buttons.items():
            is_active = key == active_key
            button.setChecked(is_active)
            button.setProperty("active", is_active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _navigate_to_page(self, key: str, *, run_mapping_check: bool = True) -> None:
        self._set_nav_active(key)
        if key in self.page_indexes:
            self.page_stack.setCurrentIndex(self.page_indexes[key])
        if key == "mapping":
            self._load_mapping_rules()

    def _set_status_badge(self, text: str, status: str) -> None:
        styles = {
            "idle": "background:#f4eee3;color:#8a6b34;border:1px solid #e2d3b7;",
            "running": "background:#efe2c6;color:#9f7833;border:1px solid #e3cfac;",
            "success": "background:#dde8e4;color:#23453c;border:1px solid #c8dcd5;",
            "failed": "background:#f3deda;color:#8b463e;border:1px solid #e7beb8;",
            "cancelled": "background:#ece7df;color:#6f675c;border:1px solid #ddd6cb;",
        }
        self.status_badge.setText(text)
        self.status_badge.setAlignment(Qt.AlignCenter)
        self.status_badge.setMinimumHeight(40)
        self.status_badge.setMinimumWidth(108)
        self.status_badge.setStyleSheet(
            "padding: 0 18px; border-radius: 999px; font-size: 13px; font-weight: 700;"
            + styles.get(status, styles["idle"])
        )

    def _set_metric_value(self, key: str, value: str) -> None:
        if key in self.metric_labels:
            self.metric_labels[key].setText(value)

    def _reset_metrics(self) -> None:
        self._set_metric_value("file_count", "0")
        self._set_metric_value("success_count", "0")
        self._set_metric_value("warning_count", "0")
        self._set_metric_value("summary_count", "0")

    def _clear_messages(self) -> None:
        self.error_table.setRowCount(0)
        self._message_candidates.clear()

    def _append_message_row(
        self,
        message_type: str,
        content: str,
        candidate: UnmappedCandidate | None = None,
    ) -> None:
        row = self.error_table.rowCount()
        self.error_table.insertRow(row)
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        check_item.setCheckState(Qt.Unchecked)
        type_item = QTableWidgetItem(message_type)
        type_item.setTextAlignment(Qt.AlignCenter)
        type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
        content_item = QTableWidgetItem(content)
        content_item.setToolTip(content)
        content_item.setFlags(content_item.flags() & ~Qt.ItemIsEditable)
        self.error_table.setItem(row, 0, check_item)
        self.error_table.setItem(row, 1, type_item)
        self.error_table.setItem(row, 2, content_item)
        if candidate is not None:
            self._message_candidates[row] = candidate

    def _row_message(self, row: int) -> str:
        message_type = self.error_table.item(row, 1)
        content = self.error_table.item(row, 2)
        left = message_type.text() if message_type is not None else ""
        right = content.text() if content is not None else ""
        return f"[{left}] {right}" if left else right

    def _checked_message_rows(self) -> list[int]:
        rows: list[int] = []
        for row in range(self.error_table.rowCount()):
            item = self.error_table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                rows.append(row)
        return rows

    def _load_defaults(self) -> None:
        input_dir = self.config_repo.get("default_input_dir", "")
        if input_dir:
            self.folder_edit.setText(input_dir)
        self._load_wps_settings()
        self._load_mapping_rules()
        self._refresh_mapping_info()

    def _load_wps_settings(self) -> None:
        self.wps_share_url_edit.setText(self.config_repo.get("wps_share_url", ""))
        self.wps_file_id_edit.setText(self.config_repo.get("wps_file_id", ""))
        self.wps_sheet_name_edit.setText(self.config_repo.get("wps_sheet_name", "正式映射"))

        self.wps_app_id_edit.setText(self.config_repo.get("wps_app_id", ""))
        self.wps_app_secret_edit.setText(self.config_repo.get("wps_app_secret", ""))
        self.wps_redirect_uri_edit.setText(self.config_repo.get("wps_redirect_uri", "http://127.0.0.1:18765/callback"))

    def _save_wps_settings(self) -> None:
        if self._is_busy():
            QMessageBox.information(self, "提示", "当前已有任务正在处理中。")
            return

        share_url = self.wps_share_url_edit.text().strip()
        file_id = self.wps_file_id_edit.text().strip()
        sheet_name = self.wps_sheet_name_edit.text().strip() or "正式映射"

        app_id = self.wps_app_id_edit.text().strip()
        app_secret = self.wps_app_secret_edit.text().strip()
        redirect_uri = self.wps_redirect_uri_edit.text().strip() or "http://127.0.0.1:18765/callback"

        if not share_url and not file_id:
            QMessageBox.warning(self, "提示", "分享链接和 file_id 至少填写一项。")
            return

        self.config_repo.set("wps_share_url", share_url)
        self.config_repo.set("wps_file_id", file_id)
        self.config_repo.set("wps_sheet_name", sheet_name)
        self.config_repo.set("wps_app_id", app_id)
        self.config_repo.set("wps_app_secret", app_secret)
        self.config_repo.set("wps_redirect_uri", redirect_uri)
        self._load_wps_settings()
        self._refresh_mapping_info()
        QMessageBox.information(self, "完成", "WPS 配置已保存。")

    def _refresh_mapping_info(self) -> None:
        local_version = self.mapping_meta_repo.get("mapping_version", "未初始化")
        cloud_version = self.mapping_meta_repo.get("mapping_cloud_version", "未检查")
        check_status = self.mapping_meta_repo.get("mapping_last_check_status", "未检查")
        check_message = self.mapping_meta_repo.get("mapping_last_check_message", "尚未执行版本检查")
        checked_at = self.mapping_meta_repo.get("mapping_last_checked_at", "未检查")
        source_url = self.mapping_meta_repo.get("mapping_source_url", "builtin://domain.classifier")
        overview_status = self._mapping_overview_status_text(check_status, check_message, cloud_version)

        self.mapping_overview_local_label.setText(f"本地版本：{local_version}")
        self.mapping_overview_cloud_label.setText(f"云端版本：{cloud_version or '未提供'}")
        self.mapping_overview_status_label.setText(f"映射状态：{overview_status}")

        self.mapping_local_version_label.setText(f"本地版本：{local_version}")
        self.mapping_cloud_version_label.setText(f"云端版本：{cloud_version or '未提供'}")
        self.mapping_check_status_label.setText(f"检查状态：{check_status} / {check_message}")
        self.mapping_checked_at_label.setText(f"最近检查：{checked_at}")
        self.mapping_source_label.setText(f"映射来源：{source_url}")

        self._set_mapping_hint(check_status, check_message, cloud_version)

    def _mapping_overview_status_text(self, status: str, message: str, cloud_version: str) -> str:
        if status == "up_to_date":
            return f"已更新到最新{f'：{cloud_version}' if cloud_version else ''}"
        if status == "update_available":
            return f"检测到云端更新{f'：{cloud_version}' if cloud_version else ''}"
        if status == "missing_cloud_version":
            return "云端未配置版本号"
        if status == "failed":
            return f"最近检查失败：{message}"
        if message:
            return message
        return "尚未执行版本检查"

    def _set_mapping_hint(self, status: str, message: str, cloud_version: str) -> None:
        if status == "update_available":
            self.mapping_hint_label.setObjectName("HintWarning")
            hint = f"检测到云端映射有更新：{cloud_version}。你可以先检查差异，再手动同步到本地缓存。"
        elif status == "up_to_date":
            self.mapping_hint_label.setObjectName("HintSuccess")
            hint = message or "本地映射已是最新版本。"
        elif status == "missing_cloud_version":
            self.mapping_hint_label.setObjectName("HintWarning")
            hint = message or "云端映射尚未配置版本号，暂时无法判断是否有更新。"
        elif status == "failed":
            self.mapping_hint_label.setObjectName("HintError")
            hint = message or "最近一次云端版本检查失败。"
        else:
            self.mapping_hint_label.setObjectName("HintNeutral")
            hint = message or "尚未执行云端版本检查。"

        self.mapping_hint_label.setText(hint)
        self.mapping_hint_label.style().unpolish(self.mapping_hint_label)
        self.mapping_hint_label.style().polish(self.mapping_hint_label)
        self.mapping_hint_label.update()

    def _load_mapping_rules(self) -> None:
        rules = self.mapping_editor_service.list_rules()
        self._loading_mapping_table = True
        self.mapping_table.setRowCount(0)
        for rule in rules:
            self._append_mapping_rule(rule)
        self.mapping_table.resizeRowsToContents()
        self._loading_mapping_table = False
        self.mapping_dirty = False

    def _append_mapping_rule(self, rule: MappingRule) -> None:
        row = self.mapping_table.rowCount()
        self.mapping_table.insertRow(row)
        values = [rule.platform, rule.remark_norm, rule.biz_desc, rule.detail_category, rule.major_category]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(str(value))
            self.mapping_table.setItem(row, column, item)

    def _is_busy(self) -> bool:
        return any(
            worker is not None
            for worker in (self.report_thread, self.sync_thread, self.check_thread, self.publish_thread)
        )

    def _choose_folder(self) -> None:
        current = self.folder_edit.text().strip()
        folder = QFileDialog.getExistingDirectory(self, "选择数据目录", current or "")
        if folder:
            self.folder_edit.setText(folder)

    def _run_report(self) -> None:
        if self._is_busy():
            QMessageBox.information(self, "提示", "当前已有任务正在处理中。")
            return

        input_dir = self.folder_edit.text().strip()
        if not input_dir:
            QMessageBox.warning(self, "提示", "请先选择数据目录。")
            return

        self.config_repo.set("default_input_dir", input_dir)
        suggested_name = build_default_export_filename()
        default_export_dir = self.config_repo.get("last_export_dir", input_dir)
        default_target = str(Path(default_export_dir) / suggested_name)

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择导出文件位置",
            default_target,
            "Excel 文件 (*.xlsx)",
        )
        if not output_path:
            self.status_label.setText("状态：已取消导出")
            self.progress_label.setText("进度：-")
            self.progress_percent_label.setText("0%")
            self._set_status_badge("已取消", "cancelled")
            return
        if not output_path.lower().endswith(".xlsx"):
            output_path += ".xlsx"

        self.config_repo.set("last_export_dir", str(Path(output_path).parent))
        self._set_running_state(True)
        self._set_status_badge("处理中", "running")
        self.status_label.setText("状态：正在处理")
        self.progress_label.setText("进度：正在准备任务...")
        self.progress_percent_label.setText("0%")
        self.progress_bar.setRange(0, 0)
        self.summary_label.setText("处理结果：-")
        self.export_label.setText("导出路径：-")
        self._reset_metrics()
        self._clear_messages()
        self._navigate_to_page("report")

        self.report_thread = QThread(self)
        self.report_worker = ReportWorker(self.run_service, input_dir, output_path)
        self.report_worker.moveToThread(self.report_thread)
        self.report_thread.started.connect(self.report_worker.run)
        self.report_worker.progress_changed.connect(self._handle_progress)
        self.report_worker.finished.connect(self._handle_run_finished)
        self.report_worker.failed.connect(self._handle_run_failed)
        self.report_worker.finished.connect(self._cleanup_report_worker)
        self.report_worker.failed.connect(self._cleanup_report_worker)
        self.report_thread.start()

    def _sync_mapping(self) -> None:
        if self._is_busy():
            QMessageBox.information(self, "提示", "当前已有任务正在处理中。")
            return
        if self.mapping_dirty:
            confirmed = QMessageBox.question(
                self,
                "覆盖提示",
                "分类映射页有未保存修改，继续同步会用云端规则覆盖当前表格，是否继续？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirmed != QMessageBox.Yes:
                return

        self._set_running_state(True)
        self._set_status_badge("同步中", "running")
        self.status_label.setText("状态：正在同步在线映射")
        self.progress_label.setText("进度：正在准备同步...")
        self.progress_percent_label.setText("同步中")
        self.progress_bar.setRange(0, 0)
        self._navigate_to_page("mapping", run_mapping_check=False)

        self.sync_thread = QThread(self)
        self.sync_worker = MappingSyncWorker(self.wps_sync_service, interactive_auth=True)
        self.sync_worker.moveToThread(self.sync_thread)
        self.sync_thread.started.connect(self.sync_worker.run)
        self.sync_worker.progress_changed.connect(self._handle_sync_progress)
        self.sync_worker.finished.connect(self._handle_sync_finished)
        self.sync_worker.failed.connect(self._handle_sync_failed)
        self.sync_worker.finished.connect(self._cleanup_sync_worker)
        self.sync_worker.failed.connect(self._cleanup_sync_worker)
        self.sync_thread.start()

    def _check_mapping_update(self, trigger: str, interactive_auth: bool, allow_modal: bool) -> None:
        if self._is_busy() or self.check_thread is not None:
            return
        self._check_context = trigger
        self._check_modal = allow_modal
        self.mapping_check_button.setEnabled(False)
        self.mapping_hint_label.setObjectName("HintNeutral")
        self.mapping_hint_label.setText("正在检查云端映射版本...")
        self.mapping_hint_label.style().unpolish(self.mapping_hint_label)
        self.mapping_hint_label.style().polish(self.mapping_hint_label)
        self.mapping_hint_label.update()

        self.check_thread = QThread(self)
        self.check_worker = MappingCheckWorker(self.wps_sync_service, interactive_auth=interactive_auth)
        self.check_worker.moveToThread(self.check_thread)
        self.check_thread.started.connect(self.check_worker.run)
        self.check_worker.finished.connect(self._handle_mapping_check_finished)
        self.check_worker.failed.connect(self._handle_mapping_check_failed)
        self.check_worker.finished.connect(self._cleanup_check_worker)
        self.check_worker.failed.connect(self._cleanup_check_worker)
        self.check_thread.start()

    def _run_startup_mapping_check(self) -> None:
        self._check_mapping_update(trigger="startup", interactive_auth=False, allow_modal=True)

    def _run_manual_mapping_check(self) -> None:
        self._check_mapping_update(trigger="manual", interactive_auth=True, allow_modal=False)

    def _save_mapping_rules(self) -> None:
        if self._is_busy():
            QMessageBox.information(self, "提示", "当前已有任务正在处理中。")
            return

        try:
            rules = self._collect_mapping_rules_from_table()
            self.mapping_editor_service.save_rules(rules)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return

        self.mapping_dirty = False
        self._refresh_mapping_info()
        self._load_mapping_rules()
        self._publish_mapping_rules()

    def _collect_mapping_rules_from_table(self) -> list[MappingRule]:
        rules: list[MappingRule] = []
        for row in range(self.mapping_table.rowCount()):
            values = [self._table_text(self.mapping_table, row, col) for col in range(len(self.MAPPING_HEADERS))]
            rules.append(
                MappingRule(
                    platform=values[0],
                    match_key="",
                    remark_norm=values[1],
                    biz_desc=values[2],
                    detail_category=values[3],
                    major_category=values[4],
                )
            )
        return rules

    def _publish_mapping_rules(self) -> None:
        rules = self.mapping_editor_service.list_rules()
        self._set_running_state(True)
        self._set_status_badge("上传中", "running")
        self.status_label.setText("状态：正在上传分类映射")
        self.progress_label.setText("进度：正在准备上传...")
        self.progress_percent_label.setText("上传中")
        self.progress_bar.setRange(0, 0)
        self._navigate_to_page("mapping", run_mapping_check=False)

        self.publish_thread = QThread(self)
        self.publish_worker = MappingPublishWorker(self.wps_sync_service, rules, interactive_auth=True)
        self.publish_worker.moveToThread(self.publish_thread)
        self.publish_thread.started.connect(self.publish_worker.run)
        self.publish_worker.progress_changed.connect(self._handle_publish_progress)
        self.publish_worker.finished.connect(self._handle_publish_finished)
        self.publish_worker.failed.connect(self._handle_publish_failed)
        self.publish_worker.finished.connect(self._cleanup_publish_worker)
        self.publish_worker.failed.connect(self._cleanup_publish_worker)
        self.publish_thread.start()

    @Slot(object)
    def _handle_progress(self, progress: RunProgress) -> None:
        self.progress_label.setText(f"进度：{progress.message}")
        if progress.total <= 0:
            self.progress_bar.setRange(0, 0)
            self.progress_percent_label.setText("扫描中")
            return
        current = min(progress.current, progress.total)
        if self.progress_bar.maximum() != progress.total:
            self.progress_bar.setRange(0, progress.total)
        self.progress_bar.setValue(current)
        percent = int(current * 100 / progress.total) if progress.total else 0
        self.progress_percent_label.setText(f"{percent}%")

    @Slot(object)
    def _handle_run_finished(self, result: RunResult) -> None:
        self._set_status_badge("已完成", "success")
        self.status_label.setText("状态：处理完成")
        self.summary_label.setText(
            "处理结果：扫描文件数 {0}，成功文件数 {1}，失败文件数 {2}，汇总行数 {3}，异常数 {4}，提醒数 {5}".format(
                result.file_count,
                result.success_count,
                result.failed_count,
                result.summary_count,
                len(result.errors),
                len(result.warnings),
            )
        )
        self.export_label.setText(f"导出路径：{result.export_path or '-'}")
        self.progress_bar.setRange(0, max(self.progress_bar.maximum(), 1))
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_label.setText("进度：处理完成")
        self.progress_percent_label.setText("100%")
        self._set_metric_value("file_count", str(result.file_count))
        self._set_metric_value("success_count", str(result.success_count))
        self._set_metric_value("warning_count", str(len(result.warnings)))
        self._set_metric_value("summary_count", str(result.summary_count))
        self._clear_messages()

        for error in result.errors:
            self._append_message_row("异常", error)
        for warning in result.warnings:
            candidate = next((item for item in result.unmapped_candidates if item.warning_message == warning), None)
            self._append_message_row("提醒", warning, candidate=candidate)
        self.error_table.resizeRowsToContents()

        self._set_running_state(False)
        if result.export_path:
            if result.warnings:
                QMessageBox.warning(self, "分类映射提醒", "\n".join(result.warnings))
            else:
                QMessageBox.information(self, "完成", "报表已生成。")

    @Slot(str)
    def _handle_run_failed(self, message: str) -> None:
        self._set_status_badge("失败", "failed")
        self.status_label.setText("状态：执行失败")
        self.progress_label.setText("进度：执行失败")
        self.progress_percent_label.setText("0%")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_running_state(False)
        QMessageBox.critical(self, "错误", message)

    @Slot(str)
    def _handle_sync_progress(self, message: str) -> None:
        self.progress_label.setText(f"进度：{message}")

    @Slot(object)
    def _handle_sync_finished(self, result: WpsSyncResult) -> None:
        self._set_status_badge("已完成", "success")
        self.status_label.setText("状态：在线映射同步完成")
        self.progress_label.setText("进度：同步完成")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_percent_label.setText("100%")
        self._set_running_state(False)
        self._refresh_mapping_info()
        self._load_mapping_rules()
        QMessageBox.information(
            self,
            "同步完成",
            "已同步 WPS 在线映射。\n"
            f"工作表：{result.worksheet_name}\n"
            f"规则数：{result.rule_count}\n"
            f"版本：{result.source_version}",
        )

    @Slot(str)
    def _handle_sync_failed(self, message: str) -> None:
        self._set_status_badge("失败", "failed")
        self.status_label.setText("状态：在线映射同步失败")
        self.progress_label.setText("进度：同步失败")
        self.progress_percent_label.setText("0%")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_running_state(False)
        self._refresh_mapping_info()
        QMessageBox.critical(self, "错误", message)

    @Slot(str)
    def _handle_publish_progress(self, message: str) -> None:
        self.progress_label.setText(f"进度：{message}")

    @Slot(object)
    def _handle_publish_finished(self, result: WpsPublishResult) -> None:
        self._set_status_badge("已完成", "success")
        self.status_label.setText("状态：分类映射已上传")
        self.progress_label.setText("进度：上传完成")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_percent_label.setText("100%")
        self._set_running_state(False)
        self._refresh_mapping_info()
        self._load_mapping_rules()
        QMessageBox.information(
            self,
            "上传完成",
            "本地映射已保存并上传到 WPS。\n"
            f"工作表：{result.worksheet_name}\n"
            f"规则数：{result.rule_count}\n"
            f"版本：{result.source_version}",
        )

    @Slot(str)
    def _handle_publish_failed(self, message: str) -> None:
        self._set_status_badge("失败", "failed")
        self.status_label.setText("状态：云端上传失败")
        self.progress_label.setText("进度：上传失败")
        self.progress_percent_label.setText("0%")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_running_state(False)
        self._refresh_mapping_info()
        QMessageBox.warning(self, "上传失败", f"本地映射已经保存，但上传云端失败：\n{message}")

    @Slot(object)
    def _handle_mapping_check_finished(self, result: WpsUpdateCheckResult) -> None:
        self.mapping_check_button.setEnabled(True)
        self._refresh_mapping_info()
        if (
            self._check_modal
            and result.status == "update_available"
            and result.cloud_version
            and result.cloud_version != self._snoozed_cloud_version
        ):
            choice = QMessageBox.question(
                self,
                "发现云端更新",
                "检测到云端分类映射有更新，是否立即同步？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if choice == QMessageBox.Yes:
                self._sync_mapping()
            else:
                self._snoozed_cloud_version = result.cloud_version
        elif self._check_context == "manual":
            if result.status == "failed":
                QMessageBox.warning(self, "检查失败", result.message)
            else:
                QMessageBox.information(self, "检查完成", result.message)

    @Slot(str)
    def _handle_mapping_check_failed(self, message: str) -> None:
        self.mapping_check_button.setEnabled(True)
        self.mapping_meta_repo.set("mapping_last_check_status", "failed")
        self.mapping_meta_repo.set("mapping_last_check_message", message)
        self._refresh_mapping_info()
        if self._check_context == "manual":
            QMessageBox.warning(self, "检查失败", message)

    @Slot()
    def _cleanup_report_worker(self) -> None:
        if self.report_thread is not None:
            self.report_thread.quit()
            self.report_thread.wait()
        if self.report_worker is not None:
            self.report_worker.deleteLater()
        if self.report_thread is not None:
            self.report_thread.deleteLater()
        self.report_worker = None
        self.report_thread = None

    @Slot()
    def _cleanup_sync_worker(self) -> None:
        if self.sync_thread is not None:
            self.sync_thread.quit()
            self.sync_thread.wait()
        if self.sync_worker is not None:
            self.sync_worker.deleteLater()
        if self.sync_thread is not None:
            self.sync_thread.deleteLater()
        self.sync_worker = None
        self.sync_thread = None

    @Slot()
    def _cleanup_check_worker(self) -> None:
        if self.check_thread is not None:
            self.check_thread.quit()
            self.check_thread.wait()
        if self.check_worker is not None:
            self.check_worker.deleteLater()
        if self.check_thread is not None:
            self.check_thread.deleteLater()
        self.check_worker = None
        self.check_thread = None

    @Slot()
    def _cleanup_publish_worker(self) -> None:
        if self.publish_thread is not None:
            self.publish_thread.quit()
            self.publish_thread.wait()
        if self.publish_worker is not None:
            self.publish_worker.deleteLater()
        if self.publish_thread is not None:
            self.publish_thread.deleteLater()
        self.publish_worker = None
        self.publish_thread = None

    def _set_running_state(self, running: bool) -> None:
        enabled = not running
        self.run_button.setEnabled(enabled)
        self.folder_button.setEnabled(enabled)
        self.folder_edit.setEnabled(enabled)
        self.mapping_check_button.setEnabled(enabled)
        self.mapping_sync_button.setEnabled(enabled)
        self.mapping_save_button.setEnabled(enabled)
        self.mapping_add_button.setEnabled(enabled)
        self.mapping_delete_button.setEnabled(enabled)
        self.wps_config_save_button.setEnabled(enabled)
        self.wps_share_url_edit.setEnabled(enabled)
        self.wps_file_id_edit.setEnabled(enabled)
        self.wps_sheet_name_edit.setEnabled(enabled)
        self.wps_app_id_edit.setEnabled(enabled)
        self.wps_app_secret_edit.setEnabled(enabled)
        self.wps_redirect_uri_edit.setEnabled(enabled)
        self.add_mapping_button.setEnabled(enabled)
        self.copy_selected_button.setEnabled(enabled)
        self.copy_all_button.setEnabled(enabled)

    def _on_mapping_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._loading_mapping_table:
            return
        self.mapping_dirty = True

    def _add_mapping_row(self) -> None:
        self._loading_mapping_table = True
        self._append_mapping_rule(
            MappingRule(
                platform="淘宝",
                match_key="",
                remark_norm="[空]",
                biz_desc="[空]",
                detail_category="",
                major_category="",
            )
        )
        self._loading_mapping_table = False
        self.mapping_dirty = True
        self.mapping_table.setCurrentCell(self.mapping_table.rowCount() - 1, 0)

    def _delete_selected_mapping_rows(self) -> None:
        rows = sorted({index.row() for index in self.mapping_table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要删除的映射行。")
            return
        self._loading_mapping_table = True
        for row in rows:
            self.mapping_table.removeRow(row)
        self._loading_mapping_table = False
        self.mapping_dirty = True

    def _copy_selected_messages(self) -> None:
        rows = self._checked_message_rows() or sorted({index.row() for index in self.error_table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "提示", "请先勾选或选中要复制的异常信息。")
            return
        self._copy_messages([self._row_message(row) for row in rows])

    def _copy_all_messages(self) -> None:
        if self.error_table.rowCount() == 0:
            QMessageBox.information(self, "提示", "当前没有可复制的异常信息。")
            return
        self._copy_messages([self._row_message(row) for row in range(self.error_table.rowCount())])

    def _copy_messages(self, messages: list[str]) -> None:
        QApplication.clipboard().setText("\n".join(messages))
        QMessageBox.information(self, "完成", f"已复制 {len(messages)} 条异常信息。")

    def _add_selected_messages_to_mapping(self) -> None:
        rows = self._checked_message_rows() or sorted({index.row() for index in self.error_table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "提示", "请先勾选或选中要加入映射的未匹配提醒。")
            return

        selected_candidates = [self._message_candidates[row] for row in rows if row in self._message_candidates]
        if not selected_candidates:
            QMessageBox.information(self, "提示", "当前选中项里没有可加入映射的未匹配提醒。")
            return

        self._navigate_to_page("mapping", run_mapping_check=False)
        existing_keys = {
            (
                self._table_text(self.mapping_table, row, 0),
                self._build_match_key_from_values(
                    self._table_text(self.mapping_table, row, 0),
                    self._table_text(self.mapping_table, row, 1),
                    self._table_text(self.mapping_table, row, 2),
                ),
            )
            for row in range(self.mapping_table.rowCount())
        }

        added_count = 0
        for candidate in selected_candidates:
            dedupe_key = (candidate.platform, candidate.match_key)
            if dedupe_key in existing_keys:
                continue
            self._loading_mapping_table = True
            self._append_mapping_rule(
                MappingRule(
                    platform=candidate.platform,
                    match_key="",
                    remark_norm=candidate.remark_norm,
                    biz_desc=candidate.biz_desc,
                    detail_category="暂未分类",
                    major_category="暂未分类",
                )
            )
            self._loading_mapping_table = False
            existing_keys.add(dedupe_key)
            added_count += 1

        if added_count <= 0:
            QMessageBox.information(self, "提示", "所选未匹配项已存在于分类映射表中。")
            return

        self.mapping_dirty = True
        self.mapping_table.resizeRowsToContents()
        self.mapping_table.setCurrentCell(self.mapping_table.rowCount() - 1, 0)
        QMessageBox.information(
            self,
            "已加入映射",
            f"已将 {added_count} 条未匹配项加入分类映射表，请检查分类后再保存并上传云端。",
        )

    def _build_match_key_from_values(self, platform: str, remark_norm: str, biz_desc: str) -> str:
        if platform == "拼多多":
            return biz_desc or "[空]"
        return f"{(remark_norm or '[空]')}{RULE_SEPARATOR}{(biz_desc or '[空]')}"

    def _table_text(self, table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text().strip() if item is not None else ""
