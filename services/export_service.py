import pandas as pd

from exporters.excel_exporter import export_summary_excel


class ExportService:
    def export(self, summary_df: pd.DataFrame, output_path: str) -> str:
        return export_summary_excel(summary_df, output_path)
