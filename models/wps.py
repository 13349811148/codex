from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class WpsSettings:
    app_id: str
    app_secret: str
    redirect_uri: str
    share_url: str
    file_id: str
    sheet_name: str


@dataclass
class WpsToken:
    access_token: str
    refresh_token: str
    token_type: str
    expires_at: int
    refresh_expires_at: int
    scopes: tuple[str, ...] = ()

    def is_expired(self, skew_seconds: int = 300) -> bool:
        return self.expires_at <= int(time.time()) + max(skew_seconds, 0)

    def refresh_expired(self, skew_seconds: int = 300) -> bool:
        return self.refresh_expires_at <= int(time.time()) + max(skew_seconds, 0)


@dataclass
class WpsWorksheet:
    sheet_id: int
    name: str
    max_row: int
    max_col: int
    active_row_from: int = 0
    active_row_to: int = 0
    active_col_from: int = 0
    active_col_to: int = 0
    index: int = 0
    hidden: bool = False
    empty: bool = False


@dataclass
class WpsSyncResult:
    file_id: str
    worksheet_id: int
    worksheet_name: str
    rule_count: int
    source_version: str


@dataclass
class WpsUpdateCheckResult:
    local_version: str
    cloud_version: str
    has_update: bool
    checked_at: str
    status: str
    message: str = ""
