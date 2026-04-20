from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re
from urllib.parse import urlparse

from models.entities import MappingRule
from models.wps import WpsSettings, WpsSyncResult, WpsWorksheet
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

            source_version = f"wps-sync-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            self.mapping_repository.replace_all_rules(rules, source_version)
            self.mapping_meta_repository.set_many(
                {
                    "mapping_version": source_version,
                    "mapping_last_sync_status": "success",
                    "mapping_last_sync_message": f"已从 WPS 在线映射同步 {len(rules)} 条规则",
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

    def _fetch_matrix(self, file_id: str, worksheet: WpsWorksheet, interactive_auth: bool) -> list[list[str]]:
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
        if not matrix:
            raise WpsSyncError(f"WPS 工作表“{worksheet.name}”未读取到任何单元格数据。")
        return matrix

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

    def _normalize_value(self, text: str) -> str:
        value = unescape(str(text or "")).strip()
        return value or self.EMPTY_TEXT

    def _cell(self, row: list[str], index: int) -> str:
        if 0 <= index < len(row):
            return str(row[index] or "")
        return ""

    def _extract_link_id(self, share_url: str) -> str:
        parsed = urlparse(share_url.strip())
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "l":
            return parts[1]
        match = re.search(r"/l/([A-Za-z0-9]+)", share_url)
        if match:
            return match.group(1)
        raise WpsSyncError("无法从 WPS 分享链接中解析 link_id。")
