from __future__ import annotations

from typing import List

from domain.file_name_parser import parse_filename
from domain.source_detector import detect_source
from models.dto import FileTask, RawRecord
from parsers.parser_factory import ParserFactory
from utils.paths import scan_supported_files


class ImportService:
    def __init__(self) -> None:
        self.parser_factory = ParserFactory()

    def scan(self, input_dir: str) -> List[FileTask]:
        tasks: List[FileTask] = []
        for file_path in scan_supported_files(input_dir):
            file_meta = parse_filename(file_path.name)
            try:
                source_type = detect_source(file_path)
            except ValueError:
                continue
            tasks.append(FileTask(path=file_path, meta=file_meta, source_type=source_type))
        return tasks

    def parse(self, task: FileTask) -> List[RawRecord]:
        parser = self.parser_factory.get(task.source_type)
        return parser.parse(str(task.path), task.meta)
