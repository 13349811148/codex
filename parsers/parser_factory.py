from parsers.pdd_csv_parser import PddCsvParser
from parsers.tb_xlsx_parser import TbXlsxParser


class ParserFactory:
    def __init__(self) -> None:
        self._parsers = {
            "pdd_table": PddCsvParser(),
            "pdd_csv": PddCsvParser(),
            "tb_table": TbXlsxParser(),
            "tb_xlsx": TbXlsxParser(),
        }

    def get(self, source_type: str):
        if source_type not in self._parsers:
            raise ValueError(f"暂不支持的来源类型: {source_type}")
        return self._parsers[source_type]
