from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
import urllib.error
import urllib.request

from services.kdocs_auth_service import KdocsAuthError, KdocsOAuthService


class KdocsApiError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, code: int = 0, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.payload = payload or {}


class KdocsOpenApiClient:
    BASE_URL = "https://developer.kdocs.cn"

    def __init__(self, auth_service: KdocsOAuthService) -> None:
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
        query = {key: value for key, value in (params or {}).items() if value is not None}
        query["access_token"] = token

        url = f"{self.BASE_URL}{path}?{urlencode(query, doseq=True)}"
        request_headers = dict(headers or {})
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
                except KdocsAuthError:
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
            raise KdocsApiError(f"金山文档 OpenAPI 请求失败：{exc}") from exc

        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            if retry_on_refresh and self._looks_like_auth_error(payload):
                try:
                    self.auth_service.refresh_access_token()
                except KdocsAuthError:
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
        return {"message": raw or exc.reason}

    def _build_error(self, status: int, payload: dict[str, Any]) -> KdocsApiError:
        code = int(payload.get("code", 0) or 0)
        message = payload.get("msg") or payload.get("message") or payload.get("result") or f"HTTP {status}"
        return KdocsApiError(f"金山文档 OpenAPI 调用失败：{message}", status=status, code=code, payload=payload)

    def _looks_like_auth_error(self, payload: dict[str, Any]) -> bool:
        text = " ".join(
            str(value)
            for value in (
                payload.get("msg"),
                payload.get("message"),
                payload.get("result"),
                payload.get("debug"),
            )
            if value
        ).lower()
        return any(keyword in text for keyword in ("token", "access_token", "refresh_token", "授权", "令牌"))
