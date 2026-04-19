from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")
EXCEL_SUFFIXES = {".xlsx", ".xls"}


def read_file_preview(file_path: str, lines: int = 8) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".csv":
        return _read_csv_preview(file_path, lines=lines)
    if suffix in EXCEL_SUFFIXES:
        return _read_excel_preview(file_path, rows=lines)
    raise ValueError(f"暂不支持的文件格式: {file_path}")


def read_pdd_table(file_path: str) -> pd.DataFrame:
    return read_structured_table(
        file_path,
        required_headers=["商户订单号", "发生时间", "收入金额（+元）", "支出金额（-元）", "业务描述"],
        preferred_sheet="原始数据",
    )


def read_tb_table(file_path: str) -> pd.DataFrame:
    return read_structured_table(
        file_path,
        required_headers=["商户订单号", "入账时间", "收入（+元）", "支出（-元）", "业务描述"],
        preferred_sheet="原始数据",
    )


def read_structured_table(file_path: str, required_headers: list[str], preferred_sheet: str | None = None) -> pd.DataFrame:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".csv":
        return _read_csv_table(file_path, required_headers)
    if suffix in EXCEL_SUFFIXES:
        return _read_excel_table(file_path, required_headers, preferred_sheet=preferred_sheet)
    raise ValueError(f"暂不支持的文件格式: {file_path}")


def _read_csv_preview(file_path: str, lines: int = 8) -> str:
    for encoding in CSV_ENCODINGS:
        try:
            with open(file_path, "r", encoding=encoding, newline="") as handle:
                return "".join(handle.readlines()[:lines])
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别 CSV 编码: {file_path}")


def _read_excel_preview(file_path: str, rows: int = 8) -> str:
    engine = "openpyxl" if Path(file_path).suffix.lower() == ".xlsx" else "xlrd"
    excel_file = pd.ExcelFile(file_path, engine=engine)
    flat: list[str] = []
    for sheet_name in excel_file.sheet_names[:2]:
        df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, nrows=rows, dtype=str)
        for row in df.fillna("").values.tolist():
            flat.extend(str(item) for item in row)
    return " ".join(flat)


def _read_csv_table(file_path: str, required_headers: list[str]) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            header_row = _find_csv_header_row(file_path, encoding, required_headers)
            return pd.read_csv(file_path, skiprows=header_row, dtype=str, encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"CSV 读取失败: {file_path}") from last_error


def _find_csv_header_row(file_path: str, encoding: str, required_headers: list[str]) -> int:
    with open(file_path, "r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        for index, row in enumerate(reader):
            if _is_header_row(row, required_headers):
                return index
    raise ValueError(f"未找到 CSV 表头: {file_path}")


def _read_excel_table(file_path: str, required_headers: list[str], preferred_sheet: str | None = None) -> pd.DataFrame:
    engine = "openpyxl" if Path(file_path).suffix.lower() == ".xlsx" else "xlrd"
    excel_file = pd.ExcelFile(file_path, engine=engine)

    sheet_names = list(excel_file.sheet_names)
    if preferred_sheet and preferred_sheet in sheet_names:
        sheet_names.remove(preferred_sheet)
        sheet_names.insert(0, preferred_sheet)

    last_error: Exception | None = None
    for sheet_name in sheet_names:
        try:
            header_row = _find_excel_header_row(excel_file, sheet_name, required_headers)
            return pd.read_excel(excel_file, sheet_name=sheet_name, header=header_row, dtype=str)
        except Exception as exc:
            last_error = exc

    raise ValueError(f"Excel 读取失败: {file_path}") from last_error


def _find_excel_header_row(excel_file: pd.ExcelFile, sheet_name: str, required_headers: list[str]) -> int:
    df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, nrows=20, dtype=str)
    for index, row in df.fillna("").iterrows():
        if _is_header_row(row.tolist(), required_headers):
            return int(index)
    raise ValueError(f"未找到 Excel 表头: {sheet_name}")


def _is_header_row(values: list[object], required_headers: list[str]) -> bool:
    normalized = {str(value).strip() for value in values if str(value).strip()}
    return all(header in normalized for header in required_headers)
