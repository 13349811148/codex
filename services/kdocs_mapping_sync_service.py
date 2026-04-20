from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from html import unescape

from models.entities import MappingRule
from models.kdocs import KdocsRecentFile, KdocsSettings, KdocsSyncResult, KdocsWorksheet
from repositories.config_repository import ConfigRepository
from repositories.mapping_meta_repository import MappingMetaRepository
from repositories.mapping_repository import MappingRepository
from services.kdocs_auth_service import KdocsOAuthService
from services.kdocs_openapi_client import KdocsOpenApiClient
from services.mapping_runtime_service import MappingRuntimeService


class KdocsSyncError(RuntimeError):
    pass


class KdocsMappingSyncService:
    EMPTY_TEXT = "[空]"
    DEFAULT_SHEET_NAME = "正式映射"
    TABLE_HEADERS = ("平台", "标准化备注", "业务描述", "明细分类", "大类")
    RECENT_LIMIT = 100

    def __init__(
        self,
        config_repo: ConfigRepository,
        mapping_repository: MappingRepository,
        mapping_meta_repository: MappingMetaRepository,
        mapping_runtime_service: MappingRuntimeService,
        auth_service: KdocsOAuthService,
        openapi_client: KdocsOpenApiClient,
    ) -> None:
        self.config_repo = config_repo
        self.mapping_repository = mapping_repository
        self.mapping_meta_repository = mapping_meta_repository
        self.mapping_runtime_service = mapping_runtime_service
        self.auth_service = auth_service
        self.openapi_client = openapi_client

    def required_scopes(self) -> list[str]:
        return ["access_personal_files"]

    def preview_sheet(
        self,
        interactive_auth: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[KdocsSettings, KdocsWorksheet, list[list[str]]]:
        settings = self.auth_service.load_settings()
        file_token, source_name = self._resolve_target_file(settings, interactive_auth, progress_callback)
        worksheet = self._resolve_worksheet(
            file_token=file_token,
            sheet_name=settings.sheet_name or self.DEFAULT_SHEET_NAME,
            interactive_auth=interactive_auth,
        )
        matrix = self._fetch_matrix(file_token, worksheet, interactive_auth)
        if progress_callback:
            progress_callback(f"已读取工作表：{source_name} / {worksheet.name}")
        return settings, worksheet, matrix

    def sync(
        self,
        interactive_auth: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> KdocsSyncResult:
        settings = self.auth_service.load_settings()
        self.mapping_repository.ensure_schema()

        try:
            if progress_callback:
                progress_callback("正在校验金山文档授权...")
            file_token, source_name = self._resolve_target_file(settings, interactive_auth, progress_callback)
            worksheet = self._resolve_worksheet(
                file_token=file_token,
                sheet_name=settings.sheet_name or self.DEFAULT_SHEET_NAME,
                interactive_auth=interactive_auth,
            )
            if progress_callback:
                progress_callback(f"正在读取工作表：{source_name} / {worksheet.name}")
            matrix = self._fetch_matrix(file_token, worksheet, interactive_auth)
            if progress_callback:
                progress_callback("正在解析在线映射规则...")
            rules = self._parse_rules(matrix)
            if not rules:
                raise KdocsSyncError("在线映射表未解析出任何有效规则，请检查“正式映射”工作表内容。")

            source_version = f"kdocs-sync-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            self.mapping_repository.replace_all_rules(rules, source_version)
            self.mapping_meta_repository.set_many(
                {
                    "mapping_version": source_version,
                    "mapping_last_sync_status": "success",
                    "mapping_last_sync_message": f"已从金山文档在线映射同步 {len(rules)} 条规则",
                    "mapping_source_url": settings.share_url or f"kdocs://file/{file_token}/sheet/{worksheet.sheet_id}",
                }
            )
            self.config_repo.set("kdocs_file_token", file_token)
            self.config_repo.set("kdocs_sheet_id", str(worksheet.sheet_id))
            self.config_repo.set("kdocs_sheet_idx", str(worksheet.sheet_idx))
            self.mapping_runtime_service.reload()
            return KdocsSyncResult(
                file_token=file_token,
                worksheet_id=worksheet.sheet_id,
                worksheet_idx=worksheet.sheet_idx,
                worksheet_name=worksheet.name,
                rule_count=len(rules),
                source_version=source_version,
                source_name=source_name,
            )
        except Exception as exc:
            self.mapping_meta_repository.set("mapping_last_sync_status", "failed")
            self.mapping_meta_repository.set("mapping_last_sync_message", str(exc))
            raise

    def _resolve_target_file(
        self,
        settings: KdocsSettings,
        interactive_auth: bool,
        progress_callback: Callable[[str], None] | None,
    ) -> tuple[str, str]:
        if settings.file_token:
            return settings.file_token, settings.file_token

        recent_files = self._list_recent_files(interactive_auth)
        candidates = sorted(recent_files, key=self._candidate_sort_key, reverse=True)
        if not candidates:
            raise KdocsSyncError("最近文档列表为空，请先在浏览器中打开目标在线表格后再重试同步。")

        sheet_name = settings.sheet_name or self.DEFAULT_SHEET_NAME
        errors: list[str] = []
        for candidate in candidates:
            if progress_callback:
                progress_callback(f"正在检查最近文档：{candidate.fname}")
            try:
                worksheet = self._resolve_worksheet(candidate.file_token, sheet_name, interactive_auth)
                preview_matrix = self._fetch_matrix(
                    candidate.file_token,
                    worksheet,
                    interactive_auth,
                    row_to=min(worksheet.max_row, 20),
                    col_to=min(worksheet.max_col, 12),
                )
                self._find_header_row(preview_matrix)
                self.config_repo.set("kdocs_file_token", candidate.file_token)
                return candidate.file_token, candidate.fname
            except Exception as exc:
                errors.append(f"{candidate.fname}: {exc}")

        raise KdocsSyncError(
            "未能在最近文档中识别到包含“正式映射”工作表的目标在线表格。"
            "请先在浏览器里打开该在线文档，确认工作表名为“正式映射”，然后重试。"
            + (f"\n最近一次检查结果：{errors[0]}" if errors else "")
        )

    def _list_recent_files(self, interactive_auth: bool) -> list[KdocsRecentFile]:
        payload = self.openapi_client.request_json(
            "GET",
            "/api/v1/openapi/personal/files/recent",
            params={"count": self.RECENT_LIMIT, "offset": 0},
            interactive_auth=interactive_auth,
            required_scopes=self.required_scopes(),
        )
        files: list[KdocsRecentFile] = []
        for item in payload.get("data", {}).get("files", []):
            file_token = str(item.get("id", {}).get("open_id") or item.get("id", {}).get("union_id") or "").strip()
            if not file_token:
                continue
            files.append(
                KdocsRecentFile(
                    file_token=file_token,
                    fname=str(item.get("fname", "")).strip(),
                    ftype=str(item.get("ftype", "")).strip(),
                    mtime=int(item.get("mtime", 0) or 0),
                )
            )
        return [item for item in files if item.ftype in {"file", "sharefile"}]

    def _candidate_sort_key(self, recent_file: KdocsRecentFile) -> tuple[int, int]:
        name = recent_file.fname.lower()
        keyword_score = 0
        if "映射" in recent_file.fname:
            keyword_score += 3
        if "维护" in recent_file.fname:
            keyword_score += 2
        if "分类" in recent_file.fname:
            keyword_score += 1
        if name.endswith((".xlsx", ".xls", ".et")):
            keyword_score += 1
        return keyword_score, recent_file.mtime

    def _resolve_worksheet(self, file_token: str, sheet_name: str, interactive_auth: bool) -> KdocsWorksheet:
        payload = self.openapi_client.request_json(
            "GET",
            f"/api/v1/openapi/ksheet/{file_token}/sheets",
            interactive_auth=interactive_auth,
            required_scopes=self.required_scopes(),
        )
        sheets = [
            KdocsWorksheet(
                sheet_id=int(item.get("sheet_id", 0) or 0),
                sheet_idx=int(item.get("sheet_idx", 0) or 0),
                name=str(item.get("sheet_name", "")).strip(),
                max_row=int(item.get("row_to", 0) or 0),
                max_col=int(item.get("col_to", 0) or 0),
                visible=bool(item.get("is_visible", True)),
                sheet_type=str(item.get("sheet_type", "et") or "et"),
            )
            for item in payload.get("data", {}).get("sheets_info", [])
        ]
        if not sheets:
            raise KdocsSyncError("文档中未读取到任何工作表。")

        target = next((sheet for sheet in sheets if sheet.name == sheet_name), None)
        if target is None:
            available = "、".join(sheet.name for sheet in sheets if sheet.name) or "无"
            raise KdocsSyncError(f"未找到工作表“{sheet_name}”。当前可用工作表：{available}")
        return target

    def _fetch_matrix(
        self,
        file_token: str,
        worksheet: KdocsWorksheet,
        interactive_auth: bool,
        *,
        row_to: int | None = None,
        col_to: int | None = None,
    ) -> list[list[str]]:
        payload = self.openapi_client.request_json(
            "GET",
            f"/api/v1/openapi/ksheet/{file_token}/sheets/{worksheet.sheet_idx}/cells",
            params={
                "row_from": 0,
                "row_to": worksheet.max_row if row_to is None else max(row_to, 0),
                "col_from": 0,
                "col_to": worksheet.max_col if col_to is None else max(col_to, 0),
            },
            interactive_auth=interactive_auth,
            required_scopes=self.required_scopes(),
        )
        matrix = self._cells_to_matrix(
            payload.get("data", {}).get("cells", []),
            worksheet.max_row if row_to is None else max(row_to, 0),
            worksheet.max_col if col_to is None else max(col_to, 0),
        )
        if not matrix:
            raise KdocsSyncError(f"工作表“{worksheet.name}”未读取到任何单元格数据。")
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
            row_end = int(cell.get("row_to", row_from) or row_from)
            col_from = int(cell.get("col_from", 0) or 0)
            col_end = int(cell.get("col_to", col_from) or col_from)
            for row_index in range(row_from, row_end + 1):
                if row_index < 0 or row_index >= row_count:
                    continue
                for col_index in range(col_from, col_end + 1):
                    if 0 <= col_index < col_count:
                        matrix[row_index][col_index] = value

        return self._trim_matrix(matrix)

    def _extract_cell_text(self, cell: dict) -> str:
        for key in ("cell_text", "origin_cell_value", "original_cell_value"):
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
        header_positions = {
            self._normalize_header(cell): index for index, cell in enumerate(header_row) if self._normalize_header(cell)
        }

        missing_headers = [header for header in self.TABLE_HEADERS if header not in header_positions]
        if missing_headers:
            raise KdocsSyncError(f"在线映射表缺少必需表头：{'、'.join(missing_headers)}")

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
                    source_version="kdocs-online",
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
        raise KdocsSyncError("未找到在线映射表表头，请确认工作表包含：平台、标准化备注、业务描述、明细分类、大类。")

    def _normalize_header(self, text: str) -> str:
        return unescape(str(text or "")).strip()

    def _normalize_value(self, text: str) -> str:
        value = unescape(str(text or "")).strip()
        return value or self.EMPTY_TEXT

    def _cell(self, row: list[str], index: int) -> str:
        if 0 <= index < len(row):
            return str(row[index] or "")
        return ""
