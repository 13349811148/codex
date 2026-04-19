from __future__ import annotations

from pathlib import Path

from utils.excel_util import read_csv_preview, read_excel_preview


def detect_source(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        preview = read_csv_preview(str(file_path), lines=6)
        if "商户订单号,发生时间,收入金额（+元）,支出金额（-元）" in preview:
            return "pdd_csv"
    elif suffix in {".xlsx", ".xls"}:
        preview = read_excel_preview(str(file_path))
        if "入账时间" in preview and "收入（+元）" in preview and "支出（-元）" in preview:
            return "tb_xlsx"

    raise ValueError(f"无法识别来源模板: {file_path.name}")
