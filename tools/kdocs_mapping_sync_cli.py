from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import build_app_services
from services.kdocs_auth_service import KdocsAuthError
from services.kdocs_mapping_sync_service import KdocsSyncError
from services.kdocs_openapi_client import KdocsApiError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="金山文档在线映射同步工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="查看当前金山文档配置与同步状态")
    status_parser.set_defaults(func=command_status)

    auth_parser = subparsers.add_parser("auth", help="发起金山文档授权")
    auth_parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    auth_parser.add_argument("--timeout", type=int, default=180, help="授权等待超时秒数，默认 180")
    auth_parser.set_defaults(func=command_auth)

    preview_parser = subparsers.add_parser("preview", help="预览正式映射工作表内容")
    preview_parser.add_argument("--interactive-auth", action="store_true", help="缺少授权时自动拉起浏览器授权")
    preview_parser.add_argument("--rows", type=int, default=6, help="预览输出的行数，默认 6")
    preview_parser.set_defaults(func=command_preview)

    sync_parser = subparsers.add_parser("sync", help="同步金山文档在线映射到本地缓存")
    sync_parser.add_argument("--interactive-auth", action="store_true", help="缺少授权时自动拉起浏览器授权")
    sync_parser.set_defaults(func=command_sync)

    return parser


def command_status(_args: argparse.Namespace) -> int:
    services = build_app_services()
    settings = services.kdocs_auth_service.load_settings()
    token = services.kdocs_auth_service.load_token()
    required_scopes = services.kdocs_mapping_sync_service.required_scopes()

    print("=== 金山文档配置状态 ===")
    print(f"APPID: {'已配置' if settings.app_id else '未配置'}")
    print(f"APPKEY: {'已配置' if settings.app_key else '未配置'}")
    print(f"redirect_uri: {settings.redirect_uri or '[未配置]'}")
    print(f"share_url: {settings.share_url or '[未配置]'}")
    print(f"file_token: {settings.file_token or '[未配置]'}")
    print(f"sheet_name: {settings.sheet_name or '[未配置]'}")
    print(f"required_scopes: {', '.join(required_scopes)}")
    print(f"access_token: {'已缓存' if token and token.access_token else '未缓存'}")
    print(f"refresh_token: {'已缓存' if token and token.refresh_token else '未缓存'}")
    print(f"token_scopes: {', '.join(token.scopes) if token and token.scopes else '[空]'}")
    print()
    print("=== 当前同步状态 ===")
    print(f"mapping_version: {services.mapping_meta_repo.get('mapping_version', '[空]')}")
    print(f"mapping_last_sync_status: {services.mapping_meta_repo.get('mapping_last_sync_status', '[空]')}")
    print(f"mapping_last_sync_message: {services.mapping_meta_repo.get('mapping_last_sync_message', '[空]')}")
    print(f"mapping_source_url: {services.mapping_meta_repo.get('mapping_source_url', '[空]')}")
    return 0


def command_auth(args: argparse.Namespace) -> int:
    services = build_app_services()
    scopes = services.kdocs_mapping_sync_service.required_scopes()
    token = services.kdocs_auth_service.authorize_interactive(
        scopes=scopes,
        timeout_seconds=max(args.timeout, 30),
        open_browser=not args.no_browser,
    )
    print("金山文档授权成功")
    print(f"token_type: {token.token_type}")
    print(f"scopes: {', '.join(token.scopes) if token.scopes else ', '.join(scopes)}")
    return 0


def command_preview(args: argparse.Namespace) -> int:
    services = build_app_services()
    settings, worksheet, matrix = services.kdocs_mapping_sync_service.preview_sheet(
        interactive_auth=args.interactive_auth
    )
    preview_rows = matrix[: max(args.rows, 1)]
    preview_cols = max((len(row) for row in preview_rows), default=0)

    print("=== 工作表预览 ===")
    print(f"share_url: {settings.share_url or '[未配置]'}")
    print(f"file_token: {services.config_repo.get('kdocs_file_token', settings.file_token or '[未缓存]')}")
    print(f"worksheet: {worksheet.name} (sheet_id={worksheet.sheet_id}, sheet_idx={worksheet.sheet_idx})")
    print(f"rows: {len(matrix)}")
    print(f"cols: {max((len(row) for row in matrix), default=0)}")
    print()
    print("=== 前几行内容 ===")
    for row_index, row in enumerate(preview_rows, start=1):
        padded = row + [""] * max(preview_cols - len(row), 0)
        print(f"{row_index:>3}: " + " | ".join(padded))
    return 0


def command_sync(args: argparse.Namespace) -> int:
    services = build_app_services()
    result = services.kdocs_mapping_sync_service.sync(interactive_auth=args.interactive_auth)
    print("金山文档在线映射同步成功")
    print(f"source_name: {result.source_name}")
    print(f"file_token: {result.file_token}")
    print(f"worksheet: {result.worksheet_name} (sheet_id={result.worksheet_id}, sheet_idx={result.worksheet_idx})")
    print(f"rule_count: {result.rule_count}")
    print(f"source_version: {result.source_version}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (KdocsAuthError, KdocsSyncError, KdocsApiError) as exc:
        print(f"ERROR: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"UNEXPECTED ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
