from __future__ import annotations

from domain.classifier import classify_record
from models.dto import NormalizedRecord
from services.mapping_runtime_service import MappingRuntimeService


class ClassifyService:
    def __init__(self, mapping_runtime_service: MappingRuntimeService) -> None:
        self.mapping_runtime_service = mapping_runtime_service

    def reload_rules(self) -> None:
        self.mapping_runtime_service.reload()

    def classify(self, record: NormalizedRecord) -> NormalizedRecord:
        return classify_record(record, self.mapping_runtime_service.get_rules_by_platform())
