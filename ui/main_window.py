from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.dto import RunProgress, RunResult
from repositories.config_repository import ConfigRepository
from services.run_report_service import RunReportService
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


class MainWindow(QMainWindow):
    def __init__(self, run_service: RunReportService, config_repo: ConfigRepository) -> None:
        super().__init__()
        self.run_service = run_service
        self.config_repo = config_repo
        self.worker_thread: QThread | None = None
        self.worker: ReportWorker | None = None
        self.setWindowTitle("财务统计小工具 V1.2")
        self.resize(900, 680)
        self._build_ui()
        self._load_defaults()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        folder_row = QHBoxLayout()
        folder_label = QLabel("数据目录:")
        self.folder_edit = QLineEdit()
        self.folder_button = QPushButton("浏览")
        self.folder_button.clicked.connect(self._choose_folder)
        folder_row.addWidget(folder_label)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(self.folder_button)

        self.run_button = QPushButton("一键生成报表")
        self.run_button.clicked.connect(self._run_report)

        self.status_label = QLabel("状态: 待执行")
        self.progress_label = QLabel("进度: -")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.summary_label = QLabel("处理结果: -")
        self.export_label = QLabel("导出路径: -")

        self.error_list = QListWidget()
        self.error_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.copy_selected_button = QPushButton("复制选中")
        self.copy_selected_button.clicked.connect(self._copy_selected_messages)
        self.copy_all_button = QPushButton("复制全部")
        self.copy_all_button.clicked.connect(self._copy_all_messages)

        copy_row = QHBoxLayout()
        copy_row.addWidget(self.copy_selected_button)
        copy_row.addWidget(self.copy_all_button)
        copy_row.addStretch()

        layout.addLayout(folder_row)
        layout.addWidget(self.run_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.export_label)
        layout.addWidget(QLabel("异常信息:"))
        layout.addLayout(copy_row)
        layout.addWidget(self.error_list)

        self.setCentralWidget(central)

    def _load_defaults(self) -> None:
        input_dir = self.config_repo.get("default_input_dir", "")
        if input_dir:
            self.folder_edit.setText(input_dir)

    def _choose_folder(self) -> None:
        current = self.folder_edit.text().strip()
        folder = QFileDialog.getExistingDirectory(self, "选择数据目录", current or "")
        if folder:
            self.folder_edit.setText(folder)

    def _run_report(self) -> None:
        if self.worker_thread is not None:
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
            self.status_label.setText("状态: 已取消导出")
            return
        if not output_path.lower().endswith(".xlsx"):
            output_path += ".xlsx"

        self.config_repo.set("last_export_dir", str(Path(output_path).parent))
        self._set_running_state(True)
        self.status_label.setText("状态: 正在处理中...")
        self.progress_label.setText("进度: 正在准备任务...")
        self.progress_bar.setRange(0, 0)
        self.summary_label.setText("处理结果: -")
        self.export_label.setText("导出路径: -")
        self.error_list.clear()

        self.worker_thread = QThread(self)
        self.worker = ReportWorker(self.run_service, input_dir, output_path)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_changed.connect(self._handle_progress)
        self.worker.finished.connect(self._handle_run_finished)
        self.worker.failed.connect(self._handle_run_failed)
        self.worker.finished.connect(self._cleanup_worker)
        self.worker.failed.connect(self._cleanup_worker)
        self.worker_thread.start()

    @Slot(object)
    def _handle_progress(self, progress: RunProgress) -> None:
        self.progress_label.setText(f"进度: {progress.message}")
        if progress.total <= 0:
            self.progress_bar.setRange(0, 0)
            return
        if self.progress_bar.maximum() != progress.total:
            self.progress_bar.setRange(0, progress.total)
        self.progress_bar.setValue(min(progress.current, progress.total))

    @Slot(object)
    def _handle_run_finished(self, result: RunResult) -> None:
        self.status_label.setText("状态: 处理完成")
        self.summary_label.setText(
            "处理结果: 扫描文件数 {0}，成功文件数 {1}，失败文件数 {2}，汇总行数 {3}，异常数 {4}，提醒数 {5}".format(
                result.file_count,
                result.success_count,
                result.failed_count,
                result.summary_count,
                len(result.errors),
                len(result.warnings),
            )
        )
        self.export_label.setText(f"导出路径: {result.export_path or '-'}")
        self.progress_bar.setRange(0, max(self.progress_bar.maximum(), 1))
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_label.setText("进度: 处理完成")

        for error in result.errors:
            QListWidgetItem(error, self.error_list)
        for warning in result.warnings:
            QListWidgetItem(f"[提醒] {warning}", self.error_list)

        self._set_running_state(False)
        if result.export_path:
            if result.warnings:
                QMessageBox.warning(self, "分类映射提醒", "\n".join(result.warnings))
            else:
                QMessageBox.information(self, "完成", "报表已生成。")

    @Slot(str)
    def _handle_run_failed(self, message: str) -> None:
        self.status_label.setText("状态: 执行失败")
        self.progress_label.setText("进度: 执行失败")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_running_state(False)
        QMessageBox.critical(self, "错误", message)

    @Slot()
    def _cleanup_worker(self) -> None:
        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait()
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None

    def _set_running_state(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.folder_button.setEnabled(not running)
        self.folder_edit.setEnabled(not running)

    def _copy_selected_messages(self) -> None:
        items = self.error_list.selectedItems()
        if not items:
            QMessageBox.information(self, "提示", "请先选择要复制的异常信息。")
            return
        self._copy_messages([item.text() for item in items])

    def _copy_all_messages(self) -> None:
        if self.error_list.count() == 0:
            QMessageBox.information(self, "提示", "当前没有可复制的异常信息。")
            return
        self._copy_messages([self.error_list.item(index).text() for index in range(self.error_list.count())])

    def _copy_messages(self, messages: list[str]) -> None:
        QApplication.clipboard().setText("\n".join(messages))
        QMessageBox.information(self, "完成", f"已复制 {len(messages)} 条异常信息。")
