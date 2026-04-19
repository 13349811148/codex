from __future__ import annotations

from pathlib import Path

from models.dto import FileMeta, RawRecord
from parsers.base_parser import BaseParser
from utils.excel_util import read_pdd_table


class PddCsvParser(BaseParser):
    def parse(self, file_path: str, file_meta: FileMeta) -> list[RawRecord]:
        df = read_pdd_table(file_path)
        source_type = f"pdd_{Path(file_path).suffix.lower().lstrip('.')}"
        source_sheet = "default" if Path(file_path).suffix.lower() == ".csv" else "原始数据"
        records: list[RawRecord] = []
        for _, row in df.iterrows():
            if _is_empty_row(row.to_dict()):
                continue
            records.append(
                RawRecord(
                    order_no=str(row.get("商户订单号", "")).strip(),
                    occur_time=str(row.get("发生时间", "")).strip(),
                    income=str(row.get("收入金额（+元）", "")).strip(),
                    expense=str(row.get("支出金额（-元）", "")).strip(),
                    remark_raw=str(row.get("备注", "")).strip(),
                    biz_desc=str(row.get("业务描述", "")).strip(),
                    account_type=str(row.get("账务类型", "")).strip(),
                    source_file=file_meta.file_name,
                    source_sheet=source_sheet,
                    source_type=source_type,
                    platform=file_meta.platform,
                    store_name=file_meta.store_name,
                )
            )
        return records


def _is_empty_row(row: dict) -> bool:
    values = [str(value).strip() for value in row.values() if value is not None]
    meaningful = [value for value in values if value and value.lower() != "nan"]
    return not meaningful
