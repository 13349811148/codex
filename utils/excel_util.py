from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_csv_preview(file_path: str, lines: int = 6) -> str:
    encodings = ("utf-8-sig", "utf-8", "gb18030", "gbk")
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as handle:
                return "".join(handle.readlines()[:lines])
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别 CSV 编码: {file_path}")


def read_pdd_csv(file_path: str) -> pd.DataFrame:
    encodings = ("utf-8-sig", "utf-8", "gb18030", "gbk")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return pd.read_csv(file_path, skiprows=4, dtype=str, encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"拼多多 CSV 读取失败: {file_path}") from last_error


def read_tb_excel(file_path: str) -> pd.DataFrame:
    engine = "openpyxl" if Path(file_path).suffix.lower() == ".xlsx" else "xlrd"
    try:
        return pd.read_excel(file_path, sheet_name="原始数据", header=2, dtype=str, engine=engine)
    except ValueError:
        return pd.read_excel(file_path, header=2, dtype=str, engine=engine)


def read_excel_preview(file_path: str) -> str:
    engine = "openpyxl" if Path(file_path).suffix.lower() == ".xlsx" else "xlrd"
    df = pd.read_excel(file_path, header=None, nrows=5, dtype=str, engine=engine)
    flat = []
    for row in df.fillna("").values.tolist():
        flat.extend(str(item) for item in row)
    return " ".join(flat)
