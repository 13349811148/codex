from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from repositories.config_repository import ConfigRepository
from services.run_report_service import RunReportService
from utils.paths import build_default_export_filename


class MainWindow(QMainWindow):
    def __init__(self, run_service: RunReportService, config_repo: ConfigRepository) -> None:
        super().__init__()
        self.run_service = run_service
        self.config_repo = config_repo
        self.setWindowTitle("财务统计小工具")
        self.resize(900, 620)
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
        self.summary_label = QLabel("处理结果: -")
        self.export_label = QLabel("导出路径: -")

        self.error_list = QListWidget()

        layout.addLayout(folder_row)
        layout.addWidget(self.run_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.export_label)
        layout.addWidget(QLabel("异常信息:"))
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

        self.run_button.setEnabled(False)
        self.status_label.setText("状态: 正在处理中...")
        self.error_list.clear()

        try:
            result = self.run_service.run(input_dir=input_dir, output_path=output_path)
            self.status_label.setText("状态: 处理完成")
            self.summary_label.setText(
                "处理结果: 扫描文件数 {0}，成功文件数 {1}，失败文件数 {2}，汇总行数 {3}，异常数 {4}".format(
                    result.file_count,
                    result.success_count,
                    result.failed_count,
                    result.summary_count,
                    len(result.errors),
                )
            )
            self.export_label.setText(f"导出路径: {result.export_path or '-'}")

            for error in result.errors:
                QListWidgetItem(error, self.error_list)

            if result.export_path:
                QMessageBox.information(self, "完成", "报表已生成。")
        except Exception as exc:  # pragma: no cover - UI fallback
            self.status_label.setText("状态: 执行失败")
            QMessageBox.critical(self, "错误", str(exc))
        finally:
            self.run_button.setEnabled(True)
