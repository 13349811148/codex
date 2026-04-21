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

from models.wps import WpsSettings, WpsToken
from repositories.config_repository import ConfigRepository


class WpsAuthError(RuntimeError):
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
  <title>WPS 授权完成</title>
  <style>
    body { font-family: "Microsoft YaHei UI", sans-serif; background: #f6f3ee; color: #2c2b27; }
    .card { max-width: 520px; margin: 80px auto; padding: 28px 32px; background: #fffdfa; border: 1px solid #ddd6cb; border-radius: 18px; }
    h1 { margin: 0 0 12px; font-size: 22px; }
    p { margin: 0; line-height: 1.8; }
  </style>
</head>
<body>
  <div class="card">
    <h1>授权结果已返回本地程序</h1>
    <p>这个窗口可以直接关闭，回到财务统计小工具继续下一步。</p>
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


class WpsOAuthService:
    AUTH_URL = "https://openapi.wps.cn/oauth2/auth"
    TOKEN_URL = "https://openapi.wps.cn/oauth2/token"
    DEFAULT_REDIRECT_URI = "http://127.0.0.1:18765/callback"
    DEFAULT_SHEET_NAME = "正式映射"

    def __init__(self, config_repo: ConfigRepository) -> None:
        self.config_repo = config_repo

    def load_settings(self) -> WpsSettings:
        return WpsSettings(
            app_id=self._read_setting("wps_app_id", "FINANCE_TOOL_WPS_APP_ID"),
            app_secret=self._read_setting("wps_app_secret", "FINANCE_TOOL_WPS_APP_SECRET"),
            redirect_uri=self._read_setting("wps_redirect_uri", "FINANCE_TOOL_WPS_REDIRECT_URI", self.DEFAULT_REDIRECT_URI),
            share_url=self._read_setting("wps_share_url", "FINANCE_TOOL_WPS_SHARE_URL"),
            file_id=self._read_setting("wps_file_id", "FINANCE_TOOL_WPS_FILE_ID"),
            sheet_name=self._read_setting("wps_sheet_name", "FINANCE_TOOL_WPS_SHEET_NAME", self.DEFAULT_SHEET_NAME),
        )

    def load_token(self) -> WpsToken | None:
        access_token = self.config_repo.get("wps_access_token", "")
        if not access_token:
            return None

        scopes = tuple(filter(None, self.config_repo.get("wps_token_scopes", "").split(",")))
        return WpsToken(
            access_token=access_token,
            refresh_token=self.config_repo.get("wps_refresh_token", ""),
            token_type=self.config_repo.get("wps_token_type", "bearer"),
            expires_at=self._safe_int(self.config_repo.get("wps_expires_at", "0")),
            refresh_expires_at=self._safe_int(self.config_repo.get("wps_refresh_expires_at", "0")),
            scopes=scopes,
        )

    def build_authorize_url(self, scopes: Iterable[str], state: str) -> str:
        settings = self.load_settings()
        self._validate_settings(settings)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": settings.app_id,
                "redirect_uri": settings.redirect_uri,
                "scope": ",".join(sorted(set(scopes))),
                "state": state,
            }
        )
        return f"{self.AUTH_URL}?{query}"

    def authorize_interactive(
        self,
        scopes: Iterable[str],
        timeout_seconds: int = 180,
        open_browser: bool = True,
    ) -> WpsToken:
        settings = self.load_settings()
        self._validate_settings(settings)
        redirect = urlparse(settings.redirect_uri)
        if redirect.scheme != "http" or not redirect.hostname or not redirect.port:
            raise WpsAuthError("redirect_uri 必须是本地 http 回调地址，例如 http://127.0.0.1:18765/callback")

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
                raise WpsAuthError("等待 WPS 授权回调超时，请确认 redirect_uri 已在 WPS 后台配置且浏览器已完成授权。")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        if callback_state.error:
            raise WpsAuthError(f"WPS 授权失败：{callback_state.error}")
        if not callback_state.code:
            raise WpsAuthError("WPS 授权未返回 code。")
        if callback_state.returned_state != state:
            raise WpsAuthError("WPS 授权回调 state 校验失败，请重新发起授权。")

        token = self.exchange_code(callback_state.code)
        self._save_token(token, scopes)
        self.config_repo.set("wps_last_authorized_at", datetime.now(timezone.utc).isoformat())
        return token

    def exchange_code(self, code: str) -> WpsToken:
        settings = self.load_settings()
        payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "client_id": settings.app_id,
                "client_secret": settings.app_secret,
                "code": code,
                "redirect_uri": settings.redirect_uri,
            }
        )
        return self._build_token(payload)

    def refresh_access_token(self) -> WpsToken:
        settings = self.load_settings()
        current = self.load_token()
        if current is None or not current.refresh_token:
            raise WpsAuthError("当前没有可用的 refresh_token，请先重新执行 WPS 授权。")
        if current.refresh_expired():
            raise WpsAuthError("refresh_token 已过期，请先重新执行 WPS 授权。")

        payload = self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": current.refresh_token,
                "client_id": settings.app_id,
                "client_secret": settings.app_secret,
            }
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

        if required_scope_set and not self._scopes_satisfied(current_scope_set, required_scope_set):
            if not interactive:
                missing = ",".join(sorted(required_scope_set - self._expand_scope_implications(current_scope_set)))
                raise WpsAuthError(f"当前 WPS token 缺少所需 scope：{missing}，请先重新授权。")
            current = self.authorize_interactive(sorted(required_scope_set))
            return current.access_token

        if current and not current.is_expired():
            return current.access_token
        if current and current.refresh_token and not current.refresh_expired():
            return self.refresh_access_token().access_token
        if interactive:
            requested_scopes = sorted(required_scope_set) if required_scope_set else list(current_scope_set) or ["kso.sheets.read"]
            return self.authorize_interactive(requested_scopes).access_token

        raise WpsAuthError("当前没有可用的 WPS access_token，请先执行授权。")

    def _scopes_satisfied(self, owned_scopes: set[str], required_scopes: set[str]) -> bool:
        return required_scopes.issubset(self._expand_scope_implications(owned_scopes))

    def _expand_scope_implications(self, scopes: set[str]) -> set[str]:
        expanded = set(scopes)
        if "kso.sheets.readwrite" in expanded:
            expanded.add("kso.sheets.read")
        return expanded

    def _token_request(self, form_data: dict[str, str]) -> dict:
        data = urlencode(form_data).encode("utf-8")
        request = urllib.request.Request(self.TOKEN_URL, data=data, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", "ignore")
            raise WpsAuthError(f"WPS token 请求失败：HTTP {exc.code} {payload}") from exc
        except urllib.error.URLError as exc:
            raise WpsAuthError(f"WPS token 请求失败：{exc}") from exc

    def _build_token(self, payload: dict) -> WpsToken:
        now = int(time.time())
        access_token = payload.get("access_token", "")
        if not access_token:
            message = payload.get("msg") or payload.get("message") or "返回中缺少 access_token"
            raise WpsAuthError(f"WPS token 响应无效：{message}")
        expires_in = self._safe_int(str(payload.get("expires_in", 0)))
        refresh_expires_in = self._safe_int(str(payload.get("refresh_expires_in", 0)))
        return WpsToken(
            access_token=access_token,
            refresh_token=payload.get("refresh_token", ""),
            token_type=payload.get("token_type", "bearer"),
            expires_at=now + expires_in,
            refresh_expires_at=now + refresh_expires_in,
        )

    def _save_token(self, token: WpsToken, scopes: Iterable[str]) -> None:
        scope_text = ",".join(sorted({scope for scope in scopes if scope}))
        self.config_repo.set("wps_access_token", token.access_token)
        self.config_repo.set("wps_refresh_token", token.refresh_token)
        self.config_repo.set("wps_token_type", token.token_type)
        self.config_repo.set("wps_expires_at", str(token.expires_at))
        self.config_repo.set("wps_refresh_expires_at", str(token.refresh_expires_at))
        self.config_repo.set("wps_token_scopes", scope_text)

    def _read_setting(self, config_key: str, env_key: str, default: str = "") -> str:
        value = os.environ.get(env_key)
        if value is not None and value.strip():
            return value.strip()
        return self.config_repo.get(config_key, default).strip()

    def has_complete_settings(self) -> bool:
        settings = self.load_settings()
        return bool(settings.app_id and settings.app_secret and settings.redirect_uri)

    def _validate_settings(self, settings: WpsSettings) -> None:
        if not settings.app_id:
            raise WpsAuthError("缺少 WPS APPID，请在软件的 WPS 配置区域填写，或设置 FINANCE_TOOL_WPS_APP_ID。")
        if not settings.app_secret:
            raise WpsAuthError("缺少 WPS APP Secret，请在软件的 WPS 配置区域填写，或设置 FINANCE_TOOL_WPS_APP_SECRET。")
        if not settings.redirect_uri:
            raise WpsAuthError("缺少 WPS 回调地址 redirect_uri，请在软件的 WPS 配置区域填写，或设置 FINANCE_TOOL_WPS_REDIRECT_URI。")

    def _safe_int(self, raw: str) -> int:
        try:
            return int(raw or 0)
        except ValueError:
            return 0
