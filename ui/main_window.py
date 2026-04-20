from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.dto import RunProgress, RunResult
from models.wps import WpsSyncResult
from repositories.config_repository import ConfigRepository
from repositories.mapping_meta_repository import MappingMetaRepository
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

    def __init__(self, wps_sync_service: WpsMappingSyncService) -> None:
        super().__init__()
        self.wps_sync_service = wps_sync_service

    @Slot()
    def run(self) -> None:
        try:
            self.progress_changed.emit("正在检查 WPS 配置...")
            self.progress_changed.emit("正在拉取在线映射，请在需要时完成浏览器授权...")
            result = self.wps_sync_service.sync(interactive_auth=True)
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - worker fallback
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(
        self,
        run_service: RunReportService,
        config_repo: ConfigRepository,
        mapping_meta_repo: MappingMetaRepository,
        wps_sync_service: WpsMappingSyncService,
    ) -> None:
        super().__init__()
        self.run_service = run_service
        self.config_repo = config_repo
        self.mapping_meta_repo = mapping_meta_repo
        self.wps_sync_service = wps_sync_service
        self.report_thread: QThread | None = None
        self.report_worker: ReportWorker | None = None
        self.sync_thread: QThread | None = None
        self.sync_worker: MappingSyncWorker | None = None
        self.metric_labels: dict[str, QLabel] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self.section_targets: dict[str, QWidget | None] = {}
        self.setWindowTitle("财务统计小工具 V1.2")
        self.resize(1320, 860)
        self.setMinimumSize(1180, 760)
        self._build_ui()
        self._load_defaults()

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("Root")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        surface = QFrame()
        surface.setObjectName("Surface")
        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)

        masthead = QFrame()
        masthead.setObjectName("Masthead")
        masthead_layout = QHBoxLayout(masthead)
        masthead_layout.setContentsMargins(0, 0, 0, 0)
        masthead_layout.setSpacing(0)

        brand_panel = QFrame()
        brand_panel.setObjectName("BrandPanel")
        brand_panel.setFixedWidth(250)
        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(24, 24, 24, 24)
        brand_layout.setSpacing(8)
        brand_layout.addStretch()
        brand_title = QLabel("财务统计小工具")
        brand_title.setObjectName("BrandTitle")
        brand_layout.addWidget(brand_title)
        brand_layout.addStretch()

        top_panel = QFrame()
        top_panel.setObjectName("TopPanel")
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(22, 18, 22, 18)
        top_layout.setSpacing(14)

        toolbar = QHBoxLayout()
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(8)
        chips_layout.addWidget(self._create_chip("V1.2", active=True))
        chips_layout.addWidget(self._create_chip("淘宝 / 天猫 / 淘工厂 / 淘农场 / 拼多多"))
        chips_layout.addWidget(self._create_chip("CSV / XLS / XLSX"))
        chips_layout.addStretch()
        toolbar.addLayout(chips_layout, 1)

        self.status_badge = QLabel()
        self.status_badge.setObjectName("StatusBadge")
        toolbar.addWidget(self.status_badge, 0, Qt.AlignRight)
        top_layout.addLayout(toolbar)

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
        self.sync_button = QPushButton("手动同步映射")
        self.sync_button.setObjectName("SecondaryButton")
        self.sync_button.clicked.connect(self._sync_mapping)
        self.run_button = QPushButton("一键生成报表")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.clicked.connect(self._run_report)
        path_row.addWidget(path_tag)
        path_row.addWidget(self.folder_edit, 1)
        path_row.addWidget(self.folder_button)
        path_row.addWidget(self.run_button)
        top_layout.addLayout(path_row)

        masthead_layout.addWidget(brand_panel)
        masthead_layout.addWidget(top_panel, 1)
        surface_layout.addWidget(masthead)

        body = QFrame()
        body.setObjectName("Body")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 20, 18, 20)
        sidebar_layout.setSpacing(14)
        side_title = QLabel("功能分区")
        side_title.setObjectName("SidebarTitle")
        sidebar_layout.addWidget(side_title)
        sidebar_layout.addWidget(self._create_nav_button("task", "报表任务", active=True))
        sidebar_layout.addWidget(self._create_nav_button("status", "运行状态"))
        sidebar_layout.addWidget(self._create_nav_button("export", "导出结果"))
        sidebar_layout.addWidget(self._create_nav_button("messages", "异常与提醒"))
        sidebar_layout.addStretch()

        main = QFrame()
        main.setObjectName("MainPanel")
        main_shell_layout = QVBoxLayout(main)
        main_shell_layout.setContentsMargins(22, 22, 22, 22)
        main_shell_layout.setSpacing(0)

        self.main_scroll = QScrollArea()
        self.main_scroll.setObjectName("MainScroll")
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setFrameShape(QFrame.NoFrame)

        main_content = QWidget()
        main_content.setObjectName("MainContent")
        main_layout = QVBoxLayout(main_content)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(18)

        metrics_layout = QGridLayout()
        metrics_layout.setHorizontalSpacing(12)
        metrics_layout.setVerticalSpacing(12)
        metrics_layout.addWidget(self._create_metric_card("file_count", "0", "扫描文件数"), 0, 0)
        metrics_layout.addWidget(self._create_metric_card("success_count", "0", "成功文件数"), 0, 1)
        metrics_layout.addWidget(self._create_metric_card("warning_count", "0", "提醒数量"), 0, 2)
        metrics_layout.addWidget(self._create_metric_card("summary_count", "0", "汇总行数"), 0, 3)
        main_layout.addLayout(metrics_layout)

        mapping_board = QFrame()
        mapping_board.setObjectName("Board")
        mapping_layout = QVBoxLayout(mapping_board)
        mapping_layout.setContentsMargins(18, 18, 18, 18)
        mapping_layout.setSpacing(12)
        mapping_head = QHBoxLayout()
        mapping_text = QVBoxLayout()
        mapping_title = QLabel("在线映射")
        mapping_title.setObjectName("BoardTitle")
        mapping_desc = QLabel("从 WPS 在线表格读取“正式映射”工作表，用最新规则覆盖本地缓存。")
        mapping_desc.setObjectName("BoardDesc")
        mapping_desc.setWordWrap(True)
        mapping_text.addWidget(mapping_title)
        mapping_text.addWidget(mapping_desc)
        mapping_head.addLayout(mapping_text, 1)
        mapping_head.addWidget(self.sync_button, 0, Qt.AlignTop)
        mapping_layout.addLayout(mapping_head)

        self.mapping_version_label = QLabel("映射版本：")
        self.mapping_version_label.setObjectName("DataLabel")
        self.mapping_status_label = QLabel("同步状态：")
        self.mapping_status_label.setObjectName("DataLabel")
        self.mapping_source_label = QLabel("映射来源：")
        self.mapping_source_label.setObjectName("DataLabel")
        self.mapping_source_label.setWordWrap(True)
        mapping_layout.addWidget(self.mapping_version_label)
        mapping_layout.addWidget(self.mapping_status_label)
        mapping_layout.addWidget(self.mapping_source_label)
        main_layout.addWidget(mapping_board)

        progress_board = QFrame()
        progress_board.setObjectName("Board")
        progress_layout = QVBoxLayout(progress_board)
        progress_layout.setContentsMargins(18, 18, 18, 18)
        progress_layout.setSpacing(12)
        progress_head = QHBoxLayout()
        progress_text = QVBoxLayout()
        progress_title = QLabel("运行进度")
        progress_title.setObjectName("BoardTitle")
        progress_desc = QLabel("处理账单时保持界面响应，实时展示状态、进度、导出路径和汇总结果。")
        progress_desc.setObjectName("BoardDesc")
        progress_desc.setWordWrap(True)
        progress_text.addWidget(progress_title)
        progress_text.addWidget(progress_desc)
        self.progress_percent_label = QLabel("0%")
        self.progress_percent_label.setObjectName("ProgressPercent")
        progress_head.addLayout(progress_text, 1)
        progress_head.addWidget(self.progress_percent_label, 0, Qt.AlignTop)
        progress_layout.addLayout(progress_head)

        self.status_label = QLabel("状态：待执行")
        self.status_label.setObjectName("DataLabel")
        self.progress_label = QLabel("进度：-")
        self.progress_label.setObjectName("DataLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        main_layout.addWidget(progress_board)
        self.section_targets["status"] = progress_board

        export_board = QFrame()
        export_board.setObjectName("Board")
        export_layout = QVBoxLayout(export_board)
        export_layout.setContentsMargins(18, 18, 18, 18)
        export_layout.setSpacing(12)
        export_title = QLabel("导出结果")
        export_title.setObjectName("BoardTitle")
        export_desc = QLabel("集中查看本次任务的汇总结果和报表导出路径，便于处理完成后立即核对。")
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
        main_layout.addWidget(export_board)
        self.section_targets["export"] = export_board

        message_board = QFrame()
        message_board.setObjectName("Board")
        message_layout = QVBoxLayout(message_board)
        message_layout.setContentsMargins(18, 18, 18, 18)
        message_layout.setSpacing(12)
        message_head = QHBoxLayout()
        message_text = QVBoxLayout()
        message_title = QLabel("异常与提醒明细")
        message_title.setObjectName("BoardTitle")
        message_desc = QLabel("按台账风格集中展示错误和分类提醒，支持复制选中记录或全部记录。")
        message_desc.setObjectName("BoardDesc")
        message_desc.setWordWrap(True)
        message_text.addWidget(message_title)
        message_text.addWidget(message_desc)
        message_head.addLayout(message_text, 1)
        self.copy_selected_button = QPushButton("复制选中")
        self.copy_selected_button.setObjectName("SecondaryButton")
        self.copy_selected_button.clicked.connect(self._copy_selected_messages)
        self.copy_all_button = QPushButton("复制全部")
        self.copy_all_button.setObjectName("SecondaryButton")
        self.copy_all_button.clicked.connect(self._copy_all_messages)
        message_head.addWidget(self.copy_selected_button)
        message_head.addWidget(self.copy_all_button)
        message_layout.addLayout(message_head)

        self.error_table = QTableWidget(0, 2)
        self.error_table.setHorizontalHeaderLabels(["类型", "内容"])
        self.error_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.error_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.error_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.error_table.setAlternatingRowColors(True)
        self.error_table.verticalHeader().setVisible(False)
        self.error_table.horizontalHeader().setStretchLastSection(True)
        self.error_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.error_table.setColumnWidth(0, 110)
        message_layout.addWidget(self.error_table)
        main_layout.addWidget(message_board, 1)
        self.section_targets["messages"] = message_board
        self.section_targets["task"] = None

        main_layout.addStretch()
        self.main_scroll.setWidget(main_content)
        main_shell_layout.addWidget(self.main_scroll)

        body_layout.addWidget(sidebar)
        body_layout.addWidget(main, 1)
        surface_layout.addWidget(body, 1)
        layout.addWidget(surface)
        self.setCentralWidget(central)
        self._set_status_badge("待运行", "idle")
        self._apply_styles()
        self._set_nav_active("task")

    def _create_chip(self, text: str, active: bool = False) -> QLabel:
        label = QLabel(text)
        label.setObjectName("ChipActive" if active else "Chip")
        return label

    def _create_nav_button(self, key: str, text: str, active: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, nav_key=key: self._navigate_to_section(nav_key))
        self.nav_buttons[key] = button
        return button

    def _set_nav_active(self, active_key: str) -> None:
        for key, button in self.nav_buttons.items():
            is_active = key == active_key
            button.setChecked(is_active)
            button.setProperty("active", is_active)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _navigate_to_section(self, key: str) -> None:
        self._set_nav_active(key)
        if key == "task":
            self.folder_edit.setFocus(Qt.TabFocusReason)
            self.main_scroll.verticalScrollBar().setValue(0)
            return

        target = self.section_targets.get(key)
        if target is not None:
            self.main_scroll.ensureWidgetVisible(target, 0, 24)

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
            QFrame#Surface { background: rgba(255, 253, 250, 0.9); border: 1px solid #ddd6cb; border-radius: 28px; }
            QFrame#BrandPanel { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #23453c,stop:1 #1a332d); }
            QLabel#BrandTitle { color: #fbfaf6; font-size: 24px; font-weight: 700; }
            QLabel#BrandSubtitle { color: rgba(255,250,246,0.75); font-size: 12px; line-height: 1.5; }
            QFrame#TopPanel, QFrame#MainPanel { background: transparent; }
            QScrollArea#MainScroll { background: transparent; border: none; }
            QWidget#MainContent { background: transparent; }
            QLabel#Chip, QLabel#ChipActive, QLabel#PathTag { padding: 8px 14px; border-radius: 999px; background: #fffdfa; border: 1px solid #ddd6cb; color: #736f67; }
            QLabel#ChipActive { background: #dde8e4; color: #23453c; font-weight: 700; border-color: #c8dcd5; }
            QLabel#PathTag { font-weight: 700; color: #5d564c; }
            QLineEdit#FolderEdit { min-height: 44px; padding: 0 14px; border: 1px solid #d7d0c5; border-radius: 12px; background: #fffdfa; color: #272621; }
            QLineEdit#FolderEdit:focus { border-color: #8b9e98; }
            QPushButton#PrimaryButton, QPushButton#SecondaryButton { min-height: 44px; padding: 0 18px; border-radius: 12px; font-weight: 700; }
            QPushButton#PrimaryButton { background: #23453c; color: #fffdfa; border: none; }
            QPushButton#PrimaryButton:hover { background: #1d3932; }
            QPushButton#SecondaryButton { background: #fffdfa; color: #3f3a33; border: 1px solid #d7d0c5; }
            QPushButton#SecondaryButton:hover { background: #f6f2ea; }
            QPushButton:disabled { background: #e7e1d8; color: #9a9387; border-color: #dfd8ce; }
            QFrame#Sidebar { background: rgba(248, 245, 239, 0.92); border-right: 1px solid #ddd6cb; }
            QLabel#SidebarTitle { color: #736f67; font-size: 12px; font-weight: 700; }
            QPushButton#NavButton { min-height: 44px; padding: 0 14px; text-align: left; border-radius: 12px; border: 1px solid transparent; background: transparent; color: #5a544b; font-weight: 600; }
            QPushButton#NavButton:hover { background: #f6f0e7; border-color: #e1d8cb; }
            QPushButton#NavButton[active="true"] { background: #fffdfa; border-color: #ddd6cb; color: #23453c; font-weight: 700; }
            QLabel#SideCard { padding: 14px; border-radius: 14px; background: #fffdfa; border: 1px solid #ddd6cb; color: #736f67; line-height: 1.7; }
            QFrame#MetricCard, QFrame#Board { background: #fffdfa; border: 1px solid #ddd6cb; border-radius: 18px; }
            QLabel#MetricValue { color: #23453c; font-size: 28px; font-weight: 700; }
            QLabel#MetricCaption { color: #736f67; font-size: 12px; }
            QLabel#BoardTitle { color: #272621; font-size: 18px; font-weight: 700; }
            QLabel#BoardDesc { color: #736f67; font-size: 13px; line-height: 1.6; }
            QLabel#ProgressPercent { color: #23453c; font-size: 26px; font-weight: 700; }
            QLabel#DataLabel { color: #403a31; font-size: 13px; line-height: 1.6; }
            QProgressBar { min-height: 12px; max-height: 12px; border: none; border-radius: 999px; background: #ece6dc; text-align: center; }
            QProgressBar::chunk { border-radius: 999px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #b18d54,stop:1 #23453c); }
            QTableWidget { border: 1px solid #ddd6cb; border-radius: 14px; gridline-color: #ebe3d8; background: #fffdfa; alternate-background-color: #faf7f1; color: #2f2b26; selection-background-color: #e7efec; selection-color: #23453c; }
            QHeaderView::section { background: #f8f5ef; padding: 10px 12px; border: none; border-bottom: 1px solid #ddd6cb; color: #736f67; font-weight: 700; }
            """
        )

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
        self.status_badge.setMinimumHeight(36)
        self.status_badge.setMinimumWidth(96)
        self.status_badge.setStyleSheet(
            "padding: 0 14px; border-radius: 999px; font-size: 12px; font-weight: 700;"
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

    def _append_message_row(self, message_type: str, content: str) -> None:
        row = self.error_table.rowCount()
        self.error_table.insertRow(row)
        type_item = QTableWidgetItem(message_type)
        type_item.setTextAlignment(Qt.AlignCenter)
        content_item = QTableWidgetItem(content)
        content_item.setToolTip(content)
        self.error_table.setItem(row, 0, type_item)
        self.error_table.setItem(row, 1, content_item)

    def _row_message(self, row: int) -> str:
        message_type = self.error_table.item(row, 0)
        content = self.error_table.item(row, 1)
        left = message_type.text() if message_type is not None else ""
        right = content.text() if content is not None else ""
        return f"[{left}] {right}" if left else right

    def _load_defaults(self) -> None:
        input_dir = self.config_repo.get("default_input_dir", "")
        if input_dir:
            self.folder_edit.setText(input_dir)
        self._refresh_mapping_info()

    def _refresh_mapping_info(self) -> None:
        mapping_version = self.mapping_meta_repo.get("mapping_version", "未初始化")
        sync_status = self.mapping_meta_repo.get("mapping_last_sync_status", "未同步")
        sync_message = self.mapping_meta_repo.get("mapping_last_sync_message", "尚未执行在线同步")
        source_url = self.mapping_meta_repo.get("mapping_source_url", "builtin://domain.classifier")
        self.mapping_version_label.setText(f"映射版本：{mapping_version}")
        self.mapping_status_label.setText(f"同步状态：{sync_status} / {sync_message}")
        self.mapping_source_label.setText(f"映射来源：{source_url}")

    def _is_busy(self) -> bool:
        return self.report_thread is not None or self.sync_thread is not None

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
            self._set_nav_active("task")
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
        self._navigate_to_section("status")

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

        self._set_running_state(True)
        self._set_status_badge("同步中", "running")
        self.status_label.setText("状态：正在同步在线映射")
        self.progress_label.setText("进度：正在准备同步...")
        self.progress_percent_label.setText("同步中")
        self.progress_bar.setRange(0, 0)
        self._navigate_to_section("status")

        self.sync_thread = QThread(self)
        self.sync_worker = MappingSyncWorker(self.wps_sync_service)
        self.sync_worker.moveToThread(self.sync_thread)
        self.sync_thread.started.connect(self.sync_worker.run)
        self.sync_worker.progress_changed.connect(self._handle_sync_progress)
        self.sync_worker.finished.connect(self._handle_sync_finished)
        self.sync_worker.failed.connect(self._handle_sync_failed)
        self.sync_worker.finished.connect(self._cleanup_sync_worker)
        self.sync_worker.failed.connect(self._cleanup_sync_worker)
        self.sync_thread.start()

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
            self._append_message_row("提醒", warning)
        self.error_table.resizeRowsToContents()

        self._set_running_state(False)
        self._navigate_to_section("export")
        if result.export_path:
            if result.warnings:
                QMessageBox.warning(self, "分类映射提醒", "\n".join(result.warnings))
            else:
                QMessageBox.information(self, "完成", "报表已生成。")

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
        self._navigate_to_section("status")
        QMessageBox.information(
            self,
            "同步完成",
            "已同步 WPS 在线映射。\n"
            f"工作表：{result.worksheet_name}\n"
            f"规则数：{result.rule_count}\n"
            f"版本：{result.source_version}",
        )

    @Slot(str)
    def _handle_run_failed(self, message: str) -> None:
        self._set_status_badge("失败", "failed")
        self.status_label.setText("状态：执行失败")
        self.progress_label.setText("进度：执行失败")
        self.progress_percent_label.setText("0%")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_running_state(False)
        self._navigate_to_section("status")
        QMessageBox.critical(self, "错误", message)

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
        self._navigate_to_section("status")
        QMessageBox.critical(self, "错误", message)

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

    def _set_running_state(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.folder_button.setEnabled(not running)
        self.folder_edit.setEnabled(not running)
        self.sync_button.setEnabled(not running)

    def _copy_selected_messages(self) -> None:
        rows = sorted({index.row() for index in self.error_table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要复制的异常信息。")
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
