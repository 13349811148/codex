from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class KdocsSettings:
    app_id: str
    app_key: str
    redirect_uri: str
    share_url: str
    file_token: str
    sheet_name: str


@dataclass
class KdocsToken:
    access_token: str
    refresh_token: str
    expires_at: int
    refresh_expires_at: int
    scopes: tuple[str, ...] = ()
    token_type: str = "bearer"

    def is_expired(self, skew_seconds: int = 300) -> bool:
        return self.expires_at <= int(time.time()) + max(skew_seconds, 0)

    def refresh_expired(self, skew_seconds: int = 300) -> bool:
        return self.refresh_expires_at <= int(time.time()) + max(skew_seconds, 0)


@dataclass
class KdocsWorksheet:
    sheet_id: int
    sheet_idx: int
    name: str
    max_row: int
    max_col: int
    visible: bool = True
    sheet_type: str = "et"


@dataclass
class KdocsRecentFile:
    file_token: str
    fname: str
    ftype: str
    mtime: int


@dataclass
class KdocsSyncResult:
    file_token: str
    worksheet_id: int
    worksheet_idx: int
    worksheet_name: str
    rule_count: int
    source_version: str
    source_name: str
