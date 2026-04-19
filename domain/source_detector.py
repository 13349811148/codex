from __future__ import annotations

from pathlib import Path

from utils.excel_util import read_file_preview


def detect_source(file_path: Path) -> str:
    preview = read_file_preview(str(file_path), lines=8)
    if "发生时间" in preview and "收入金额（+元）" in preview and "支出金额（-元）" in preview:
        return "pdd_table"
    if "入账时间" in preview and "收入（+元）" in preview and "支出（-元）" in preview:
        return "tb_table"

    raise ValueError(f"无法识别来源模板: {file_path.name}")
