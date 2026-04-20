from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
import urllib.error
import urllib.request

from services.wps_auth_service import WpsAuthError, WpsOAuthService


class WpsApiError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, code: int = 0, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.payload = payload or {}


class WpsOpenApiClient:
    BASE_URL = "https://openapi.wps.cn"

    def __init__(self, auth_service: WpsOAuthService) -> None:
        self.auth_service = auth_service

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        interactive_auth: bool = False,
        required_scopes: list[str] | None = None,
        retry_on_refresh: bool = True,
    ) -> dict[str, Any]:
        token = self.auth_service.get_valid_access_token(required_scopes=required_scopes, interactive=interactive_auth)
        url = f"{self.BASE_URL}{path}"
        if params:
            url = f"{url}?{urlencode({key: value for key, value in params.items() if value is not None})}"

        request_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            request_headers.update(headers)

        body = None
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=body, method=method.upper())
        for key, value in request_headers.items():
            request.add_header(key, value)

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = self._read_error_payload(exc)
            if exc.code == 401 and retry_on_refresh:
                try:
                    self.auth_service.refresh_access_token()
                except WpsAuthError:
                    pass
                else:
                    return self.request_json(
                        method,
                        path,
                        params=params,
                        json_body=json_body,
                        headers=headers,
                        interactive_auth=interactive_auth,
                        required_scopes=required_scopes,
                        retry_on_refresh=False,
                    )
            raise self._build_error(exc.code, payload) from exc
        except urllib.error.URLError as exc:
            raise WpsApiError(f"WPS OpenAPI 请求失败：{exc}") from exc

        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise self._build_error(200, payload)
        return payload

    def _read_error_payload(self, exc: urllib.error.HTTPError) -> dict[str, Any]:
        raw = exc.read().decode("utf-8", "ignore")
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        return {"msg": raw or exc.reason}

    def _build_error(self, status: int, payload: dict[str, Any]) -> WpsApiError:
        code = int(payload.get("code", 0) or 0)
        message = payload.get("msg") or payload.get("message") or f"HTTP {status}"
        return WpsApiError(f"WPS OpenAPI 调用失败：{message}", status=status, code=code, payload=payload)
