from __future__ import annotations

from domain.classifier import iter_builtin_mapping_rules
from repositories.mapping_meta_repository import MappingMetaRepository
from repositories.mapping_repository import MappingRepository


class MappingRuntimeService:
    BUILTIN_VERSION = "builtin-default-v1"

    def __init__(
        self,
        mapping_repository: MappingRepository,
        mapping_meta_repository: MappingMetaRepository,
    ) -> None:
        self.mapping_repository = mapping_repository
        self.mapping_meta_repository = mapping_meta_repository
        self._rules_by_platform: dict[str, dict[str, tuple[str, str]]] = {}

    def ensure_seeded(self) -> None:
        self.mapping_repository.ensure_schema()
        if self.mapping_repository.count_rules() == 0:
            self.mapping_repository.replace_all_rules(iter_builtin_mapping_rules(), self.BUILTIN_VERSION)
            self.mapping_meta_repository.set_many(
                {
                    "mapping_version": self.BUILTIN_VERSION,
                    "mapping_last_sync_status": "seeded",
                    "mapping_last_sync_message": "已从内置默认映射初始化本地缓存",
                    "mapping_source_url": "builtin://domain.classifier",
                }
            )
        elif not self.mapping_meta_repository.get("mapping_version"):
            self.mapping_meta_repository.set("mapping_version", self.BUILTIN_VERSION)
            self.mapping_meta_repository.set("mapping_last_sync_status", "legacy_cache")
            self.mapping_meta_repository.set("mapping_last_sync_message", "已沿用现有本地缓存映射")
            self.mapping_meta_repository.set("mapping_source_url", "local://mapping_rules")

        self.reload()

    def reload(self) -> None:
        rules_by_platform: dict[str, dict[str, tuple[str, str]]] = {}
        for rule in self.mapping_repository.list_enabled_rules():
            platform_rules = rules_by_platform.setdefault(rule.platform, {})
            platform_rules[rule.match_key] = (rule.detail_category, rule.major_category)
        self._rules_by_platform = rules_by_platform

    def get_rules_by_platform(self) -> dict[str, dict[str, tuple[str, str]]]:
        return self._rules_by_platform
