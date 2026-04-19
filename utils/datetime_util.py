from __future__ import annotations

from datetime import datetime


def extract_month(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("时间字段为空")

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            continue
    raise ValueError(f"无法解析时间字段: {text}")
