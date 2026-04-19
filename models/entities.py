from dataclasses import dataclass


@dataclass
class MappingRule:
    platform: str
    match_key: str
    detail_category: str
    major_category: str
    enabled: bool = True
