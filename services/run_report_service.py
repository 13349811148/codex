from __future__ import annotations

from typing import List

from domain.amount_normalizer import normalize_amount
from domain.remark_normalizer import normalize_taobao_remark
from models.dto import NormalizedRecord, RunResult
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

    def run(self, input_dir: str, output_path: str) -> RunResult:
        errors: List[str] = []
        normalized_records: List[NormalizedRecord] = []
        success_count = 0
        failed_count = 0

        tasks = self.import_service.scan(input_dir)
        for task in tasks:
            try:
                raw_records = self.import_service.parse(task)
                for raw in raw_records:
                    try:
                        amount = normalize_amount(raw.income, raw.expense)
                        month = extract_month(raw.occur_time)
                        remark_norm = normalize_taobao_remark(raw.remark_raw) if raw.platform == "淘宝" else (raw.remark_raw or "").strip()

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
                        normalized_records.append(record)
                    except Exception as record_exc:
                        errors.append(f"{task.path.name}: {record_exc}")
                success_count += 1
            except Exception as exc:
                failed_count += 1
                errors.append(f"{task.path.name}: {exc}")

        summary_df = self.aggregate_service.aggregate(normalized_records)
        export_path = self.export_service.export(summary_df, output_path)

        result = RunResult(
            file_count=len(tasks),
            success_count=success_count,
            failed_count=failed_count,
            summary_count=len(summary_df.index),
            export_path=export_path,
            errors=errors,
        )
        self.run_log_repo.add_run(
            input_dir=input_dir,
            file_count=result.file_count,
            success_count=result.success_count,
            failed_count=result.failed_count,
            export_path=result.export_path,
            status="success" if not failed_count else "partial_success",
            message=f"errors={len(errors)}",
        )
        return result
