from dataclasses import dataclass


@dataclass
class MappingRule:
    platform: str
    match_key: str
    remark_norm: str
    biz_desc: str
    detail_category: str
    major_category: str
    source_version: str = ""
    enabled: bool = True
