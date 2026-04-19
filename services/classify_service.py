from domain.classifier import classify_record
from models.dto import NormalizedRecord


class ClassifyService:
    def classify(self, record: NormalizedRecord) -> NormalizedRecord:
        return classify_record(record)
