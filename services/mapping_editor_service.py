from __future__ import annotations

from datetime import datetime, timezone

from domain.classifier import TAOBAO_LIKE_PLATFORMS, RULE_SEPARATOR
from models.dto import MappingSaveResult
from models.entities import MappingRule
from repositories.mapping_meta_repository import MappingMetaRepository
from repositories.mapping_repository import MappingRepository
from services.mapping_runtime_service import MappingRuntimeService


class MappingEditorService:
    SUPPORTED_PLATFORMS = ("拼多多", "淘宝", "天猫", "淘工厂", "淘农场")
    EMPTY_TEXT = "[空]"

    def __init__(
        self,
        mapping_repository: MappingRepository,
        mapping_meta_repository: MappingMetaRepository,
        mapping_runtime_service: MappingRuntimeService,
    ) -> None:
        self.mapping_repository = mapping_repository
        self.mapping_meta_repository = mapping_meta_repository
        self.mapping_runtime_service = mapping_runtime_service

    def list_rules(self) -> list[MappingRule]:
        self.mapping_repository.ensure_schema()
        return self.mapping_repository.list_enabled_rules()

    def save_rules(self, raw_rules: list[MappingRule]) -> MappingSaveResult:
        rules = self._normalize_rules(raw_rules)
        if not rules:
            raise ValueError("至少需要保留一条有效映射规则。")

        source_version = f"local-edit-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        self.mapping_repository.replace_all_rules(rules, source_version)
        self.mapping_meta_repository.set_many(
            {
                "mapping_version": source_version,
                "mapping_last_sync_status": "local_saved",
                "mapping_last_sync_message": f"已保存 {len(rules)} 条本地映射规则",
                "mapping_source_url": "local://mapping_rules",
            }
        )
        self.mapping_runtime_service.reload()
        return MappingSaveResult(
            rule_count=len(rules),
            source_version=source_version,
            message=f"已保存 {len(rules)} 条本地映射规则。",
        )

    def _normalize_rules(self, raw_rules: list[MappingRule]) -> list[MappingRule]:
        normalized: list[MappingRule] = []
        seen_keys: set[tuple[str, str]] = set()

        for index, rule in enumerate(raw_rules, start=1):
            platform = str(rule.platform or "").strip()
            remark_norm = self._normalize_text(rule.remark_norm)
            biz_desc = self._normalize_text(rule.biz_desc)
            detail_category = str(rule.detail_category or "").strip()
            major_category = str(rule.major_category or "").strip()

            if not any((platform, detail_category, major_category, remark_norm != self.EMPTY_TEXT, biz_desc != self.EMPTY_TEXT)):
                continue
            if not platform:
                raise ValueError(f"第 {index} 行缺少平台。")
            if platform not in self.SUPPORTED_PLATFORMS:
                raise ValueError(f"第 {index} 行平台“{platform}”不受支持。")
            if not detail_category:
                raise ValueError(f"第 {index} 行缺少明细分类。")
            if not major_category:
                raise ValueError(f"第 {index} 行缺少大类。")

            if platform == "拼多多":
                remark_norm = self.EMPTY_TEXT
                if biz_desc == self.EMPTY_TEXT:
                    raise ValueError(f"第 {index} 行拼多多规则缺少业务描述。")
                match_key = biz_desc
            else:
                if platform not in TAOBAO_LIKE_PLATFORMS:
                    raise ValueError(f"第 {index} 行平台“{platform}”暂不支持编辑。")
                if remark_norm == self.EMPTY_TEXT and biz_desc == self.EMPTY_TEXT:
                    raise ValueError(f"第 {index} 行标准化备注和业务描述不能同时为空。")
                match_key = f"{remark_norm}{RULE_SEPARATOR}{biz_desc}"

            dedupe_key = (platform, match_key)
            if dedupe_key in seen_keys:
                raise ValueError(f"第 {index} 行与其他规则重复：{platform} / {match_key}")
            seen_keys.add(dedupe_key)
            normalized.append(
                MappingRule(
                    platform=platform,
                    match_key=match_key,
                    remark_norm=remark_norm,
                    biz_desc=biz_desc,
                    detail_category=detail_category,
                    major_category=major_category,
                    source_version=rule.source_version,
                    enabled=True,
                )
            )
        return normalized

    def _normalize_text(self, value: str) -> str:
        text = str(value or "").strip()
        return text or self.EMPTY_TEXT
