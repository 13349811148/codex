from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileMeta:
    file_path: str
    file_name: str
    platform: str
    store_name: str


@dataclass
class FileTask:
    path: Path
    meta: FileMeta
    source_type: str


@dataclass
class RawRecord:
    order_no: str
    occur_time: str
    income: str
    expense: str
    remark_raw: str
    biz_desc: str
    account_type: str
    source_file: str
    source_sheet: str
    source_type: str
    platform: str
    store_name: str


@dataclass
class NormalizedRecord:
    month: str
    store_name: str
    platform: str
    order_no: str
    amount: float
    remark_norm: str
    biz_desc: str
    detail_category: str
    major_category: str
    ignored: bool
    error_message: str
    warning_message: str
    source_file: str
    source_sheet: str
    source_type: str


@dataclass
class RunResult:
    file_count: int
    success_count: int
    failed_count: int
    summary_count: int
    export_path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RunProgress:
    message: str
    current: int
    total: int
