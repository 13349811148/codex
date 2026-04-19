from __future__ import annotations

from typing import Callable, List

from domain.amount_normalizer import normalize_amount
from domain.classifier import TAOBAO_LIKE_PLATFORMS
from domain.remark_normalizer import normalize_taobao_remark
from models.dto import NormalizedRecord, RunProgress, RunResult
from repositories.config_repository import ConfigRepository
from repositories.run_log_repository import RunLogRepository
from services.aggregate_service import AggregateService
from services.classify_service import ClassifyService
from services.export_service import ExportService
from services.import_service import ImportService
from utils.datetime_util import extract_month


class RunReportService:
    def __init__(self, config_repo: ConfigRepository, run_log_repo: RunLogRepository) -> None:
        self.config_repo = config_repo
        self.run_log_repo = run_log_repo
        self.import_service = ImportService()
        self.classify_service = ClassifyService()
        self.aggregate_service = AggregateService()
        self.export_service = ExportService()

    def run(
        self,
        input_dir: str,
        output_path: str,
        progress_callback: Callable[[RunProgress], None] | None = None,
    ) -> RunResult:
        errors: List[str] = []
        warnings: list[str] = []
        seen_warnings: set[str] = set()
        normalized_records: List[NormalizedRecord] = []
        success_count = 0
        failed_count = 0

        self._emit_progress(progress_callback, "正在扫描数据目录...", 0, 0)
        tasks = self.import_service.scan(input_dir)
        total_units = max(len(tasks), 1) * 100 + 20
        self._emit_progress(progress_callback, f"已扫描到 {len(tasks)} 个账单文件", 5, total_units)

        for task in tasks:
            file_index = success_count + failed_count + 1
            base_progress = (file_index - 1) * 100
            try:
                self._emit_progress(
                    progress_callback,
                    f"正在读取第 {file_index}/{len(tasks)} 个文件: {task.path.name}",
                    base_progress + 10,
                    total_units,
                )
                raw_records = self.import_service.parse(task)
                self._emit_progress(
                    progress_callback,
                    f"正在处理第 {file_index}/{len(tasks)} 个文件: {task.path.name}，共 {len(raw_records)} 条记录",
                    base_progress + 25,
                    total_units,
                )
                progress_step = max(len(raw_records) // 20, 1) if raw_records else 1
                for processed_index, raw in enumerate(raw_records, start=1):
                    try:
                        amount = normalize_amount(raw.income, raw.expense)
                        month = extract_month(raw.occur_time)
                        if raw.platform in TAOBAO_LIKE_PLATFORMS:
                            remark_norm = normalize_taobao_remark(raw.remark_raw)
                        else:
                            remark_norm = (raw.remark_raw or "").strip()

                        record = NormalizedRecord(
                            month=month,
                            store_name=raw.store_name,
                            platform=raw.platform,
                            order_no=raw.order_no,
                            amount=amount,
                            remark_norm=remark_norm or "[空]",
                            biz_desc=(raw.biz_desc or "").strip() or "[空]",
                            detail_category="",
                            major_category="",
                            ignored=False,
                            error_message="",
                            warning_message="",
                            source_file=raw.source_file,
                            source_sheet=raw.source_sheet,
                            source_type=raw.source_type,
                        )
                        record = self.classify_service.classify(record)
                        if record.error_message:
                            errors.append(record.error_message)
                            continue
                        if record.ignored:
                            continue
                        if record.warning_message and record.warning_message not in seen_warnings:
                            seen_warnings.add(record.warning_message)
                            warnings.append(record.warning_message)
                        normalized_records.append(record)
                    except Exception as record_exc:
                        errors.append(f"{task.path.name}: {record_exc}")
                    if raw_records and (processed_index % progress_step == 0 or processed_index == len(raw_records)):
                        current = base_progress + 25 + int(processed_index / len(raw_records) * 70)
                        self._emit_progress(
                            progress_callback,
                            f"正在处理第 {file_index}/{len(tasks)} 个文件: {task.path.name} ({processed_index}/{len(raw_records)})",
                            current,
                            total_units,
                        )
                success_count += 1
                self._emit_progress(
                    progress_callback,
                    f"已完成第 {file_index}/{len(tasks)} 个文件: {task.path.name}",
                    base_progress + 100,
                    total_units,
                )
            except Exception as exc:
                failed_count += 1
                errors.append(f"{task.path.name}: {exc}")
                self._emit_progress(
                    progress_callback,
                    f"文件处理失败: {task.path.name}",
                    base_progress + 100,
                    total_units,
                )

        self._emit_progress(progress_callback, "正在汇总统计结果...", total_units - 10, total_units)
        summary_df = self.aggregate_service.aggregate(normalized_records)
        self._emit_progress(progress_callback, "正在导出 Excel 报表...", total_units - 5, total_units)
        export_path = self.export_service.export(summary_df, output_path)

        result = RunResult(
            file_count=len(tasks),
            success_count=success_count,
            failed_count=failed_count,
            summary_count=len(summary_df.index),
            export_path=export_path,
            errors=errors,
            warnings=warnings,
        )
        self.run_log_repo.add_run(
            input_dir=input_dir,
            file_count=result.file_count,
            success_count=result.success_count,
            failed_count=result.failed_count,
            export_path=result.export_path,
            status="success" if not failed_count else "partial_success",
            message=f"errors={len(errors)},warnings={len(warnings)}",
        )
        self._emit_progress(progress_callback, "处理完成", total_units, total_units)
        return result

    def _emit_progress(
        self,
        progress_callback: Callable[[RunProgress], None] | None,
        message: str,
        current: int,
        total: int,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(RunProgress(message=message, current=current, total=total))
