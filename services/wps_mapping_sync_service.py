from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from html import unescape
import re
from urllib.parse import urlparse

from models.entities import MappingRule
from models.wps import WpsPublishResult, WpsSettings, WpsSyncResult, WpsUpdateCheckResult, WpsWorksheet
from repositories.config_repository import ConfigRepository
from repositories.mapping_meta_repository import MappingMetaRepository
from repositories.mapping_repository import MappingRepository
from services.mapping_runtime_service import MappingRuntimeService
from services.wps_auth_service import WpsOAuthService
from services.wps_openapi_client import WpsApiError, WpsOpenApiClient


class WpsSyncError(RuntimeError):
    pass


class WpsMappingSyncService:
    EMPTY_TEXT = "[空]"
    DEFAULT_SHEET_NAME = "正式映射"
    TABLE_HEADERS = ("平台", "标准化备注", "业务描述", "明细分类", "大类")
    META_VERSION_KEYS = {"mapping_version", "云端版本", "映射版本"}
    META_UPDATED_AT_KEYS = {"updated_at", "更新时间"}
    UPDATE_CHUNK_SIZE = 200

    def __init__(
        self,
        config_repo: ConfigRepository,
        mapping_repository: MappingRepository,
        mapping_meta_repository: MappingMetaRepository,
        mapping_runtime_service: MappingRuntimeService,
        auth_service: WpsOAuthService,
        openapi_client: WpsOpenApiClient,
    ) -> None:
        self.config_repo = config_repo
        self.mapping_repository = mapping_repository
        self.mapping_meta_repository = mapping_meta_repository
        self.mapping_runtime_service = mapping_runtime_service
        self.auth_service = auth_service
        self.openapi_client = openapi_client

    def required_scopes(self) -> list[str]:
        settings = self.auth_service.load_settings()
        scopes = ["kso.sheets.read"]
        if not settings.file_id and settings.share_url:
            scopes.append("kso.file_link.readwrite")
        return scopes

    def preview_sheet(self, interactive_auth: bool = False) -> tuple[WpsSettings, WpsWorksheet, list[list[str]]]:
        settings = self.auth_service.load_settings()
        file_id = self._resolve_file_id(settings, interactive_auth)
        worksheet = self._resolve_worksheet(file_id, settings.sheet_name or self.DEFAULT_SHEET_NAME, interactive_auth)
        matrix = self._fetch_matrix(file_id, worksheet, interactive_auth)
        return settings, worksheet, matrix

    def check_update(self, interactive_auth: bool = False) -> WpsUpdateCheckResult:
        checked_at = datetime.now(timezone.utc).isoformat()
        local_version = self.mapping_meta_repository.get("mapping_version", "")
        try:
            settings, worksheet, matrix = self.preview_sheet(interactive_auth=interactive_auth)
            cloud_version, updated_at = self._extract_cloud_metadata(matrix)
            if not cloud_version:
                result = WpsUpdateCheckResult(
                    local_version=local_version,
                    cloud_version="",
                    has_update=False,
                    checked_at=checked_at,
                    status="missing_cloud_version",
                    message="云端映射未配置 mapping_version 元数据，暂时无法判断是否有更新。",
                )
            else:
                has_update = cloud_version != local_version
                result = WpsUpdateCheckResult(
                    local_version=local_version,
                    cloud_version=cloud_version,
                    has_update=has_update,
                    checked_at=checked_at,
                    status="update_available" if has_update else "up_to_date",
                    message=(
                        f"检测到云端映射新版本：{cloud_version}"
                        if has_update
                        else f"云端映射已是最新版本：{cloud_version}"
                    ),
                )

            self.mapping_meta_repository.set_many(
                {
                    "mapping_cloud_version": result.cloud_version,
                    "mapping_cloud_updated_at": updated_at,
                    "mapping_last_check_status": result.status,
                    "mapping_last_check_message": result.message,
                    "mapping_last_checked_at": checked_at,
                    "mapping_source_url": settings.share_url or f"wps://file/{self._resolve_file_id(settings, interactive_auth)}/sheet/{worksheet.sheet_id}",
                }
            )
            return result
        except Exception as exc:
            self.mapping_meta_repository.set_many(
                {
                    "mapping_last_check_status": "failed",
                    "mapping_last_check_message": str(exc),
                    "mapping_last_checked_at": checked_at,
                }
            )
            return WpsUpdateCheckResult(
                local_version=local_version,
                cloud_version="",
                has_update=False,
                checked_at=checked_at,
                status="failed",
                message=str(exc),
            )

    def sync(self, interactive_auth: bool = False) -> WpsSyncResult:
        settings = self.auth_service.load_settings()
        self.mapping_repository.ensure_schema()
        try:
            file_id = self._resolve_file_id(settings, interactive_auth)
            worksheet = self._resolve_worksheet(file_id, settings.sheet_name or self.DEFAULT_SHEET_NAME, interactive_auth)
            matrix = self._fetch_matrix(file_id, worksheet, interactive_auth)
            rules = self._parse_rules(matrix)
            if not rules:
                raise WpsSyncError("在线映射表未解析出任何有效规则，请检查“正式映射”工作表内容。")

            cloud_version, updated_at = self._extract_cloud_metadata(matrix)
            source_version = cloud_version or f"wps-sync-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            self.mapping_repository.replace_all_rules(rules, source_version)
            self.mapping_meta_repository.set_many(
                {
                    "mapping_version": source_version,
                    "mapping_cloud_version": cloud_version or source_version,
                    "mapping_cloud_updated_at": updated_at,
                    "mapping_last_sync_status": "success",
                    "mapping_last_sync_message": f"已从 WPS 在线映射同步 {len(rules)} 条规则",
                    "mapping_last_check_status": "up_to_date",
                    "mapping_last_check_message": f"已同步到版本 {source_version}",
                    "mapping_last_checked_at": datetime.now(timezone.utc).isoformat(),
                    "mapping_source_url": settings.share_url or f"wps://file/{file_id}/sheet/{worksheet.sheet_id}",
                }
            )
            self.config_repo.set("wps_file_id", file_id)
            self.config_repo.set("wps_sheet_id", str(worksheet.sheet_id))
            self.mapping_runtime_service.reload()
            return WpsSyncResult(
                file_id=file_id,
                worksheet_id=worksheet.sheet_id,
                worksheet_name=worksheet.name,
                rule_count=len(rules),
                source_version=source_version,
            )
        except Exception as exc:
            self.mapping_meta_repository.set("mapping_last_sync_status", "failed")
            self.mapping_meta_repository.set("mapping_last_sync_message", str(exc))
            raise

    def publish_rules(
        self,
        rules: list[MappingRule],
        *,
        interactive_auth: bool = False,
        source_version: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> WpsPublishResult:
        settings = self.auth_service.load_settings()
        self.mapping_repository.ensure_schema()
        if not rules:
            raise WpsSyncError("没有可上传的映射规则。")

        publish_version = source_version or f"cloud-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        updated_at = datetime.now(timezone.utc).isoformat()

        try:
            if progress_callback:
                progress_callback("正在校验 WPS 授权与工作表...")
            file_id = self._resolve_file_id(settings, interactive_auth)
            worksheet = self._resolve_worksheet(file_id, settings.sheet_name or self.DEFAULT_SHEET_NAME, interactive_auth)

            if progress_callback:
                progress_callback("正在读取云端映射现有内容...")
            current_matrix = self._fetch_matrix(file_id, worksheet, interactive_auth, allow_empty=True)
            target_matrix = self._build_publish_matrix(rules, publish_version, updated_at)
            operations = self._build_update_operations(current_matrix, target_matrix)

            if operations:
                if progress_callback:
                    progress_callback(f"正在写回云端映射，共 {len(operations)} 个单元格变更...")
                self._submit_update_operations(file_id, worksheet.sheet_id, operations, interactive_auth)
            elif progress_callback:
                progress_callback("云端映射内容无差异，正在刷新版本信息...")

            self.mapping_repository.replace_all_rules(rules, publish_version)
            self.mapping_meta_repository.set_many(
                {
                    "mapping_version": publish_version,
                    "mapping_cloud_version": publish_version,
                    "mapping_cloud_updated_at": updated_at,
                    "mapping_last_sync_status": "success",
                    "mapping_last_sync_message": f"已保存并上传 {len(rules)} 条映射规则到 WPS",
                    "mapping_last_check_status": "up_to_date",
                    "mapping_last_check_message": f"云端映射已更新到版本 {publish_version}",
                    "mapping_last_checked_at": updated_at,
                    "mapping_source_url": self._build_source_url(settings, file_id, worksheet.sheet_id),
                }
            )
            self.config_repo.set("wps_file_id", file_id)
            self.config_repo.set("wps_sheet_id", str(worksheet.sheet_id))
            self.mapping_runtime_service.reload()
            return WpsPublishResult(
                file_id=file_id,
                worksheet_id=worksheet.sheet_id,
                worksheet_name=worksheet.name,
                rule_count=len(rules),
                source_version=publish_version,
                updated_at=updated_at,
                operation_count=len(operations),
            )
        except Exception as exc:
            self.mapping_meta_repository.set("mapping_last_sync_status", "upload_failed")
            self.mapping_meta_repository.set("mapping_last_sync_message", f"本地已保存，但上传云端失败：{exc}")
            raise

    def _resolve_file_id(self, settings: WpsSettings, interactive_auth: bool) -> str:
        if settings.file_id:
            return settings.file_id
        if not settings.share_url:
            raise WpsSyncError("缺少 WPS 分享链接或 file_id，无法读取在线映射。")

        link_id = self._extract_link_id(settings.share_url)
        try:
            payload = self.openapi_client.request_json(
                "GET",
                f"/v7/links/{link_id}/meta",
                interactive_auth=interactive_auth,
                required_scopes=["kso.file_link.readwrite"],
            )
        except WpsApiError as exc:
            raise WpsSyncError(
                "当前无法从分享链接解析 file_id。"
                "这通常是因为 open.wps.cn 对该 kdocs 私有短链没有返回文件元信息。"
                "请先确认应用已开通 `kso.file_link.readwrite`，"
                "如果仍失败，请直接写入 `wps_file_id`，例如执行："
                "`python tools/mapping_sync_cli.py set-file-id <file_id>`。"
            ) from exc

        file_id = str(payload.get("data", {}).get("file_id", "")).strip()
        if not file_id:
            raise WpsSyncError("WPS 分享链接信息中未返回 file_id。")
        return file_id

    def _resolve_worksheet(self, file_id: str, sheet_name: str, interactive_auth: bool) -> WpsWorksheet:
        payload = self.openapi_client.request_json(
            "GET",
            f"/v7/sheets/{file_id}/worksheets",
            interactive_auth=interactive_auth,
            required_scopes=["kso.sheets.read"],
        )
        sheets = [
            WpsWorksheet(
                sheet_id=int(item.get("sheet_id", 0)),
                name=str(item.get("name", "")).strip(),
                max_row=int(item.get("max_row", 0) or 0),
                max_col=int(item.get("max_col", 0) or 0),
                active_row_from=int(item.get("active_area", {}).get("row_from", 0) or 0),
                active_row_to=int(item.get("active_area", {}).get("row_to", 0) or 0),
                active_col_from=int(item.get("active_area", {}).get("col_from", 0) or 0),
                active_col_to=int(item.get("active_area", {}).get("col_to", 0) or 0),
                index=int(item.get("index", 0) or 0),
                hidden=bool(item.get("hidden", False)),
                empty=bool(item.get("empty", False)),
            )
            for item in payload.get("data", {}).get("sheets", [])
        ]
        if not sheets:
            raise WpsSyncError("WPS 文件中未读取到任何工作表。")

        target = next((sheet for sheet in sheets if sheet.name == sheet_name), None)
        if target is None:
            available = "、".join(sheet.name for sheet in sheets if sheet.name) or "无"
            raise WpsSyncError(f"未找到工作表“{sheet_name}”。当前可用工作表：{available}")
        return target

    def _fetch_matrix(
        self,
        file_id: str,
        worksheet: WpsWorksheet,
        interactive_auth: bool,
        *,
        allow_empty: bool = False,
    ) -> list[list[str]]:
        row_to = worksheet.active_row_to if worksheet.active_row_to >= worksheet.active_row_from else worksheet.max_row
        col_to = worksheet.active_col_to if worksheet.active_col_to >= worksheet.active_col_from else worksheet.max_col
        payload = self.openapi_client.request_json(
            "GET",
            f"/v7/sheets/{file_id}/worksheets/{worksheet.sheet_id}/range_data",
            params={
                "row_from": max(worksheet.active_row_from, 0),
                "row_to": max(row_to, 0),
                "col_from": max(worksheet.active_col_from, 0),
                "col_to": max(col_to, 0),
            },
            interactive_auth=interactive_auth,
            required_scopes=["kso.sheets.read"],
        )
        matrix = self._cells_to_matrix(
            payload.get("data", {}).get("range_data", []),
            max(row_to, 0),
            max(col_to, 0),
        )
        if not matrix and not allow_empty:
            raise WpsSyncError(f"WPS 工作表“{worksheet.name}”未读取到任何单元格数据。")
        return matrix

    def _build_publish_matrix(
        self,
        rules: list[MappingRule],
        source_version: str,
        updated_at: str,
    ) -> list[list[str]]:
        matrix: list[list[str]] = [
            ["mapping_version", source_version],
            ["updated_at", updated_at],
            [],
            list(self.TABLE_HEADERS),
        ]
        for rule in rules:
            matrix.append(
                [
                    rule.platform,
                    self._display_value(rule.remark_norm),
                    self._display_value(rule.biz_desc),
                    rule.detail_category,
                    rule.major_category,
                ]
            )
        return matrix

    def _build_update_operations(
        self,
        current_matrix: list[list[str]],
        target_matrix: list[list[str]],
    ) -> list[dict[str, object]]:
        row_count = max(len(current_matrix), len(target_matrix))
        col_count = max(
            max((len(row) for row in current_matrix), default=0),
            max((len(row) for row in target_matrix), default=0),
        )
        operations: list[dict[str, object]] = []
        for row_index in range(row_count):
            for col_index in range(col_count):
                current_value = self._matrix_value(current_matrix, row_index, col_index)
                target_value = self._matrix_value(target_matrix, row_index, col_index)
                if current_value == target_value:
                    continue
                operations.append(
                    {
                        "row_from": row_index,
                        "row_to": row_index,
                        "col_from": col_index,
                        "col_to": col_index,
                        "op_type": "cell_operation_type_formula",
                        "formula": target_value,
                    }
                )
        return operations

    def _submit_update_operations(
        self,
        file_id: str,
        worksheet_id: int,
        operations: list[dict[str, object]],
        interactive_auth: bool,
    ) -> None:
        for start in range(0, len(operations), self.UPDATE_CHUNK_SIZE):
            batch = operations[start : start + self.UPDATE_CHUNK_SIZE]
            self.openapi_client.request_json(
                "POST",
                f"/v7/sheets/{file_id}/worksheets/{worksheet_id}/range_data/batch_update",
                json_body={"range_data": batch},
                interactive_auth=interactive_auth,
                required_scopes=["kso.sheets.readwrite"],
            )

    def _extract_cloud_metadata(self, matrix: list[list[str]]) -> tuple[str, str]:
        metadata: dict[str, str] = {}
        for row in matrix[:10]:
            for index, cell in enumerate(row[:-1]):
                key = self._normalize_meta_key(cell)
                if not key:
                    continue
                value = str(row[index + 1] or "").strip()
                if value:
                    metadata.setdefault(key, value)
        return metadata.get("mapping_version", ""), metadata.get("updated_at", "")

    def _cells_to_matrix(self, cells: list[dict], max_row: int, max_col: int) -> list[list[str]]:
        last_row = max((int(cell.get("row_to", -1) or -1) for cell in cells), default=-1)
        last_col = max((int(cell.get("col_to", -1) or -1) for cell in cells), default=-1)
        row_count = max(max_row, last_row) + 1
        col_count = max(max_col, last_col) + 1
        if row_count <= 0 or col_count <= 0:
            return []

        matrix = [["" for _ in range(col_count)] for _ in range(row_count)]
        for cell in cells:
            value = self._extract_cell_text(cell)
            row_from = int(cell.get("row_from", 0) or 0)
            row_to = int(cell.get("row_to", row_from) or row_from)
            col_from = int(cell.get("col_from", 0) or 0)
            col_to = int(cell.get("col_to", col_from) or col_from)
            for row_index in range(row_from, row_to + 1):
                if row_index < 0 or row_index >= row_count:
                    continue
                for col_index in range(col_from, col_to + 1):
                    if 0 <= col_index < col_count:
                        matrix[row_index][col_index] = value

        return self._trim_matrix(matrix)

    def _extract_cell_text(self, cell: dict) -> str:
        for key in ("cell_text", "original_cell_value", "pic_content", "pic_data"):
            raw = cell.get(key)
            if raw not in (None, ""):
                return str(raw).strip()
        return ""

    def _trim_matrix(self, matrix: list[list[str]]) -> list[list[str]]:
        last_row = -1
        last_col = -1
        for row_index, row in enumerate(matrix):
            for col_index, value in enumerate(row):
                if str(value).strip():
                    last_row = max(last_row, row_index)
                    last_col = max(last_col, col_index)
        if last_row < 0 or last_col < 0:
            return []
        return [[str(value).strip() for value in row[: last_col + 1]] for row in matrix[: last_row + 1]]

    def _parse_rules(self, matrix: list[list[str]]) -> list[MappingRule]:
        header_row_index = self._find_header_row(matrix)
        header_row = matrix[header_row_index]
        header_positions = {self._normalize_header(cell): index for index, cell in enumerate(header_row) if self._normalize_header(cell)}

        missing_headers = [header for header in self.TABLE_HEADERS if header not in header_positions]
        if missing_headers:
            raise WpsSyncError(f"在线映射表缺少必需表头：{'、'.join(missing_headers)}")

        rules: list[MappingRule] = []
        for row in matrix[header_row_index + 1 :]:
            if not any(str(cell).strip() for cell in row):
                continue

            platform = self._cell(row, header_positions["平台"]).strip()
            remark_norm = self._normalize_value(self._cell(row, header_positions["标准化备注"]))
            biz_desc = self._normalize_value(self._cell(row, header_positions["业务描述"]))
            detail_category = self._cell(row, header_positions["明细分类"]).strip()
            major_category = self._cell(row, header_positions["大类"]).strip()

            if not platform:
                continue
            if not detail_category or not major_category:
                continue
            if remark_norm == self.EMPTY_TEXT and biz_desc == self.EMPTY_TEXT:
                continue

            match_key = biz_desc if platform == "拼多多" else f"{remark_norm} —— {biz_desc}"
            rules.append(
                MappingRule(
                    platform=platform,
                    match_key=match_key,
                    remark_norm=remark_norm,
                    biz_desc=biz_desc,
                    detail_category=detail_category,
                    major_category=major_category,
                    source_version="wps-online",
                    enabled=True,
                )
            )
        return rules

    def _find_header_row(self, matrix: list[list[str]]) -> int:
        expected = set(self.TABLE_HEADERS)
        for index, row in enumerate(matrix):
            headers = {self._normalize_header(cell) for cell in row if self._normalize_header(cell)}
            if expected.issubset(headers):
                return index
        raise WpsSyncError("未找到在线映射表表头，请确认工作表包含：平台、标准化备注、业务描述、明细分类、大类。")

    def _normalize_header(self, text: str) -> str:
        return unescape(str(text or "")).strip()

    def _normalize_meta_key(self, text: str) -> str:
        value = unescape(str(text or "")).strip()
        if value in self.META_VERSION_KEYS:
            return "mapping_version"
        if value in self.META_UPDATED_AT_KEYS:
            return "updated_at"
        return ""

    def _normalize_value(self, text: str) -> str:
        value = unescape(str(text or "")).strip()
        return value or self.EMPTY_TEXT

    def _display_value(self, text: str) -> str:
        value = unescape(str(text or "")).strip()
        return "" if value == self.EMPTY_TEXT else value

    def _matrix_value(self, matrix: list[list[str]], row_index: int, col_index: int) -> str:
        if 0 <= row_index < len(matrix) and 0 <= col_index < len(matrix[row_index]):
            return str(matrix[row_index][col_index] or "").strip()
        return ""

    def _cell(self, row: list[str], index: int) -> str:
        if 0 <= index < len(row):
            return str(row[index] or "")
        return ""

    def _build_source_url(self, settings: WpsSettings, file_id: str, worksheet_id: int) -> str:
        return settings.share_url or f"wps://file/{file_id}/sheet/{worksheet_id}"

    def _extract_link_id(self, share_url: str) -> str:
        parsed = urlparse(share_url.strip())
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "l":
            return parts[1]
        match = re.search(r"/l/([A-Za-z0-9]+)", share_url)
        if match:
            return match.group(1)
        raise WpsSyncError("无法从 WPS 分享链接中解析 link_id。")
