from __future__ import annotations

import pandas as pd

from models.dto import NormalizedRecord


SUMMARY_COLUMNS = ["月份", "店铺名", "平台", "大类", "明细分类", "金额", "记录数"]


def aggregate_records(records: list[NormalizedRecord]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    data = [
        {
            "month": record.month,
            "store_name": record.store_name,
            "platform": record.platform,
            "major_category": record.major_category,
            "detail_category": record.detail_category,
            "amount": record.amount,
        }
        for record in records
    ]
    df = pd.DataFrame(data)

    grouped = (
        df.groupby(["month", "store_name", "platform", "major_category", "detail_category"], dropna=False)
        .agg(
            金额=("amount", "sum"),
            记录数=("amount", "size"),
        )
        .reset_index()
    )

    result = grouped.rename(
        columns={
            "month": "月份",
            "store_name": "店铺名",
            "platform": "平台",
            "major_category": "大类",
            "detail_category": "明细分类",
        }
    )
    return result[SUMMARY_COLUMNS].sort_values(["月份", "店铺名", "平台", "大类", "明细分类"]).reset_index(drop=True)
