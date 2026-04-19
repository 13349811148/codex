from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font

from utils.paths import ensure_directory


def export_summary_excel(summary_df: pd.DataFrame, output_path: str | None = None) -> str:
    if output_path:
        file_path = Path(output_path)
        ensure_directory(str(file_path.parent))
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_dir = ensure_directory(str(Path.cwd() / "exports"))
        file_path = Path(default_dir) / f"财务汇总报表_{timestamp}.xlsx"

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="总汇总表")
        sheet = writer.book["总汇总表"]
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max_length + 2, 28)

    return str(file_path)
