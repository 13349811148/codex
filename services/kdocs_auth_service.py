from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import threading
import time
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlparse
import urllib.error
import urllib.request
import webbrowser

from models.kdocs import KdocsSettings, KdocsToken
from repositories.config_repository import ConfigRepository


class KdocsAuthError(RuntimeError):
    pass


@dataclass
class _CallbackState:
    event: threading.Event
    code: str = ""
    error: str = ""
    returned_state: str = ""


class _CallbackServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], callback_path: str, state: _CallbackState) -> None:
        super().__init__(server_address, _CallbackHandler)
        self.callback_path = callback_path
        self.state = state


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer

    def do_GET(self) -> None:  # pragma: no cover - interactive flow
        parsed = urlparse(self.path)
        if parsed.path != self.server.callback_path:
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        self.server.state.code = params.get("code", [""])[0]
        self.server.state.error = params.get("error", [""])[0]
        self.server.state.returned_state = params.get("state", [""])[0]
        self.server.state.event.set()

        html = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>金山文档授权完成</title>
  <style>
    body { font-family: "Microsoft YaHei UI", sans-serif; background: #f6f3ee; color: #2c2b27; }
    .card { max-width: 520px; margin: 80px auto; padding: 28px 32px; background: #fffdfa; border: 1px solid #ddd6cb; border-radius: 18px; }
    h1 { margin: 0 0 12px; font-size: 22px; }
    p { margin: 0; line-height: 1.8; }
  </style>
</head>
<body>
  <div class="card">
    <h1>授权结果已返回本机</h1>
    <p>这个窗口可以直接关闭，回到财务统计工具继续下一步。</p>
  </div>
</body>
</html>
"""
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class KdocsOAuthService:
    AUTH_URL = "https://developer.kdocs.cn/h5/auth"
    TOKEN_URL = "https://developer.kdocs.cn/api/v1/oauth2/access_token"
    REFRESH_URL = "https://developer.kdocs.cn/api/v1/oauth2/refresh_token"
    DEFAULT_REDIRECT_URI = "http://127.0.0.1:18765/callback"
    DEFAULT_SHEET_NAME = "正式映射"
    DEFAULT_REFRESH_EXPIRES_IN = 90 * 24 * 60 * 60

    def __init__(self, config_repo: ConfigRepository) -> None:
        self.config_repo = config_repo

    def load_settings(self) -> KdocsSettings:
        return KdocsSettings(
            app_id=self._read_setting(
                config_keys=("kdocs_app_id", "wps_app_id"),
                env_keys=("FINANCE_TOOL_KDOCS_APP_ID", "FINANCE_TOOL_WPS_APP_ID"),
            ),
            app_key=self._read_setting(
                config_keys=("kdocs_app_key", "wps_app_secret"),
                env_keys=("FINANCE_TOOL_KDOCS_APP_KEY", "FINANCE_TOOL_WPS_APP_SECRET"),
            ),
            redirect_uri=self._read_setting(
                config_keys=("kdocs_redirect_uri", "wps_redirect_uri"),
                env_keys=("FINANCE_TOOL_KDOCS_REDIRECT_URI", "FINANCE_TOOL_WPS_REDIRECT_URI"),
                default=self.DEFAULT_REDIRECT_URI,
            ),
            share_url=self._read_setting(
                config_keys=("kdocs_share_url", "wps_share_url"),
                env_keys=("FINANCE_TOOL_KDOCS_SHARE_URL", "FINANCE_TOOL_WPS_SHARE_URL"),
            ),
            file_token=self._read_setting(
                config_keys=("kdocs_file_token",),
                env_keys=("FINANCE_TOOL_KDOCS_FILE_TOKEN",),
            ),
            sheet_name=self._read_setting(
                config_keys=("kdocs_sheet_name", "wps_sheet_name"),
                env_keys=("FINANCE_TOOL_KDOCS_SHEET_NAME", "FINANCE_TOOL_WPS_SHEET_NAME"),
                default=self.DEFAULT_SHEET_NAME,
            ),
        )

    def load_token(self) -> KdocsToken | None:
        access_token = self.config_repo.get("kdocs_access_token", "").strip()
        if not access_token:
            return None

        scopes = tuple(filter(None, self.config_repo.get("kdocs_token_scopes", "").split(",")))
        return KdocsToken(
            access_token=access_token,
            refresh_token=self.config_repo.get("kdocs_refresh_token", "").strip(),
            expires_at=self._safe_int(self.config_repo.get("kdocs_expires_at", "0")),
            refresh_expires_at=self._safe_int(self.config_repo.get("kdocs_refresh_expires_at", "0")),
            scopes=scopes,
        )

    def build_authorize_url(self, scopes: Iterable[str], state: str) -> str:
        settings = self.load_settings()
        self._validate_settings(settings)
        query = urlencode(
            {
                "app_id": settings.app_id,
                "scope": ",".join(sorted({scope for scope in scopes if scope})),
                "redirect_uri": settings.redirect_uri,
                "state": state,
            }
        )
        return f"{self.AUTH_URL}?{query}"

    def authorize_interactive(
        self,
        scopes: Iterable[str],
        timeout_seconds: int = 180,
        open_browser: bool = True,
    ) -> KdocsToken:
        settings = self.load_settings()
        self._validate_settings(settings)
        redirect = urlparse(settings.redirect_uri)
        if redirect.scheme != "http" or not redirect.hostname or not redirect.port:
            raise KdocsAuthError("redirect_uri 必须是本机 http 回调地址，例如 http://127.0.0.1:18765/callback")

        state = secrets.token_urlsafe(16)
        callback_state = _CallbackState(event=threading.Event())
        server = _CallbackServer((redirect.hostname, redirect.port), redirect.path or "/", callback_state)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        thread.start()

        auth_url = self.build_authorize_url(scopes, state)
        try:
            if open_browser:  # pragma: no cover - interactive flow
                opened = webbrowser.open(auth_url)
                if not opened and os.name == "nt":
                    os.startfile(auth_url)  # type: ignore[attr-defined]
            if not callback_state.event.wait(timeout_seconds):
                raise KdocsAuthError("等待金山文档授权回调超时，请确认 redirect_uri 已在后台配置并完成浏览器授权。")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        if callback_state.error:
            raise KdocsAuthError(f"金山文档授权失败：{callback_state.error}")
        if not callback_state.code:
            raise KdocsAuthError("金山文档授权未返回 code。")
        if callback_state.returned_state != state:
            raise KdocsAuthError("金山文档授权回调 state 校验失败，请重新发起授权。")

        token = self.exchange_code(callback_state.code)
        self._save_token(token, scopes)
        self.config_repo.set("kdocs_last_authorized_at", datetime.now(timezone.utc).isoformat())
        return token

    def exchange_code(self, code: str) -> KdocsToken:
        settings = self.load_settings()
        payload = self._request_json(
            "GET",
            self.TOKEN_URL,
            params={
                "code": code,
                "app_id": settings.app_id,
                "app_key": settings.app_key,
            },
        )
        return self._build_token(payload)

    def refresh_access_token(self) -> KdocsToken:
        settings = self.load_settings()
        current = self.load_token()
        if current is None or not current.refresh_token:
            raise KdocsAuthError("当前没有可用的 refresh_token，请先重新执行金山文档授权。")
        if current.refresh_expired():
            raise KdocsAuthError("refresh_token 已过期，请先重新执行金山文档授权。")

        payload = self._request_json(
            "POST",
            self.REFRESH_URL,
            params={"app_id": settings.app_id},
            json_body={
                "app_key": settings.app_key,
                "refresh_token": current.refresh_token,
            },
        )
        refreshed = self._build_token(payload)
        self._save_token(refreshed, current.scopes)
        return refreshed

    def get_valid_access_token(
        self,
        required_scopes: Iterable[str] | None = None,
        interactive: bool = False,
    ) -> str:
        required_scope_set = {scope for scope in (required_scopes or []) if scope}
        current = self.load_token()
        current_scope_set = set(current.scopes) if current else set()

        if required_scope_set and not required_scope_set.issubset(current_scope_set):
            if not interactive:
                missing = ",".join(sorted(required_scope_set - current_scope_set))
                raise KdocsAuthError(f"当前金山文档 token 缺少所需 scope：{missing}，请先重新授权。")
            current = self.authorize_interactive(sorted(required_scope_set))
            return current.access_token

        if current and not current.is_expired():
            return current.access_token
        if current and current.refresh_token and not current.refresh_expired():
            return self.refresh_access_token().access_token
        if interactive:
            requested_scopes = sorted(required_scope_set) if required_scope_set else list(current_scope_set) or [
                "access_personal_files"
            ]
            return self.authorize_interactive(requested_scopes).access_token

        raise KdocsAuthError("当前没有可用的金山文档 access_token，请先执行授权。")

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, str] | None = None,
    ) -> dict:
        final_url = url
        if params:
            final_url = f"{final_url}?{urlencode({key: value for key, value in params.items() if value is not None})}"

        body = None
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(final_url, data=body, method=method.upper())
        request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "ignore")
            raise KdocsAuthError(f"金山文档授权请求失败：HTTP {exc.code} {raw}") from exc
        except urllib.error.URLError as exc:
            raise KdocsAuthError(f"金山文档授权请求失败：{exc}") from exc

        if not isinstance(payload, dict):
            raise KdocsAuthError("金山文档授权响应格式无效。")
        if payload.get("code") not in (None, 0):
            message = payload.get("msg") or payload.get("message") or payload.get("result") or "未知错误"
            raise KdocsAuthError(f"金山文档授权失败：{message}")
        return payload

    def _build_token(self, payload: dict) -> KdocsToken:
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        access_token = str(data.get("access_token", "")).strip()
        if not access_token:
            raise KdocsAuthError("金山文档授权响应缺少 access_token。")

        now = int(time.time())
        expires_in = self._safe_int(str(data.get("expires_in", 0)))
        return KdocsToken(
            access_token=access_token,
            refresh_token=str(data.get("refresh_token", "")).strip(),
            expires_at=now + expires_in,
            refresh_expires_at=now + self.DEFAULT_REFRESH_EXPIRES_IN,
        )

    def _save_token(self, token: KdocsToken, scopes: Iterable[str]) -> None:
        scope_text = ",".join(sorted({scope for scope in scopes if scope}))
        self.config_repo.set("kdocs_access_token", token.access_token)
        self.config_repo.set("kdocs_refresh_token", token.refresh_token)
        self.config_repo.set("kdocs_expires_at", str(token.expires_at))
        self.config_repo.set("kdocs_refresh_expires_at", str(token.refresh_expires_at))
        self.config_repo.set("kdocs_token_scopes", scope_text)

    def _read_setting(self, config_keys: tuple[str, ...], env_keys: tuple[str, ...], default: str = "") -> str:
        for env_key in env_keys:
            value = os.environ.get(env_key)
            if value and value.strip():
                return value.strip()
        for config_key in config_keys:
            value = self.config_repo.get(config_key, "")
            if value and value.strip():
                return value.strip()
        return default.strip()

    def _validate_settings(self, settings: KdocsSettings) -> None:
        if not settings.app_id:
            raise KdocsAuthError("缺少金山文档 APPID，请设置 FINANCE_TOOL_KDOCS_APP_ID 或写入本地配置。")
        if not settings.app_key:
            raise KdocsAuthError("缺少金山文档 APPKEY，请设置 FINANCE_TOOL_KDOCS_APP_KEY 或写入本地配置。")
        if not settings.redirect_uri:
            raise KdocsAuthError("缺少金山文档 redirect_uri，请设置 FINANCE_TOOL_KDOCS_REDIRECT_URI。")

    def _safe_int(self, raw: str) -> int:
        try:
            return int(raw or 0)
        except ValueError:
            return 0
