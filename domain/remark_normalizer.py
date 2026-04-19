from __future__ import annotations

import re


def normalize_taobao_remark(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "[空]"

    if text.startswith("代扣款（扣款用途："):
        match = re.search(r"代扣款（扣款用途：([^_，]+)", text)
        if match:
            return f"{match.group(1).strip()}扣款"

    text = re.sub(r"（全渠道）", "", text)
    text = re.sub(r"\(KY_ITEM\)", "", text)
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    text = re.sub(r"-\d{6,}.*$", "", text)
    text = re.sub(r"关联订单号：\d+", "", text)
    text = re.sub(r"=tb\d+", "", text)
    text = re.sub(r"[-_]+$", "", text)
    text = re.sub(r"\s+", "", text)
    return text or "[空]"
