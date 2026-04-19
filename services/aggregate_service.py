import pandas as pd

from domain.aggregator import aggregate_records
from models.dto import NormalizedRecord


class AggregateService:
    def aggregate(self, records: list[NormalizedRecord]) -> pd.DataFrame:
        return aggregate_records(records)
