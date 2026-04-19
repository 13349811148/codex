from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path


APP_DIR_NAME = "FinanceTool"


def get_app_home() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    base_dir = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
    path = base_dir / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_database_path() -> Path:
    return get_app_home() / "app.db"


def get_default_output_dir(input_dir: str) -> str:
    output_dir = Path(input_dir) / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir)


def ensure_directory(path: str) -> str:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def scan_supported_files(input_dir: str) -> list[Path]:
    root = Path(input_dir)
    files = []
    for path in root.iterdir():
        if path.is_file() and path.suffix.lower() in {".csv", ".xls", ".xlsx"}:
            files.append(path)
    return sorted(files, key=lambda item: item.name)


def build_default_export_filename() -> str:
    return f"财务汇总报表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
