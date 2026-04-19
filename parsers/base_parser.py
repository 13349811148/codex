from __future__ import annotations

from abc import ABC, abstractmethod

from models.dto import FileMeta, RawRecord


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str, file_meta: FileMeta) -> list[RawRecord]:
        raise NotImplementedError
