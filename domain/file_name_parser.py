from __future__ import annotations

import re

from models.dto import FileMeta


PLATFORMS = ("拼多多", "淘宝", "天猫", "京东")


def parse_filename(file_name: str) -> FileMeta:
    stem = re.sub(r"\.[^.]+$", "", file_name)
    stem = stem.replace("（下载）", "").replace("(下载)", "")
    stem = re.sub(r"^\d+月", "", stem)

    platform = "未知平台"
    for candidate in PLATFORMS:
        if candidate in stem:
            platform = candidate
            break

    store_name = "未知店铺"
    if platform != "未知平台":
        parts = re.split(rf"{platform}", stem, maxsplit=1)
        if len(parts) == 2:
            right = parts[1]
            right = re.sub(r"^[—\-_\s]+", "", right)
            right = right.strip()
            if right:
                store_name = right

    return FileMeta(file_path="", file_name=file_name, platform=platform, store_name=store_name)
