from __future__ import annotations

import re


EMPTY_TEXT = "[空]"
ORDER_ID_MIN_LENGTH = 10


def normalize_taobao_remark(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return EMPTY_TEXT

    extracted = _extract_withholding_purpose(text)
    if extracted:
        return extracted

    text = re.sub(r"（全渠道）|\(全渠道\)", "", text)
    text = re.sub(r"（KY_ITEM）|\(KY_ITEM\)", "", text)
    text = re.sub(r"[（(][^（）()]*[）)]", "", text)

    text = re.sub(r"[-_=:：，,;；\s]*(?:关联|业务基础|业务|商户)?订单号[:：=]?[A-Za-z0-9_-]+", "", text)
    text = re.sub(r"=tb\d+", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"[-_=:：，,;；\s]*\d{{{ORDER_ID_MIN_LENGTH},}}[-_=:：，,;；\s]*", "", text)

    text = re.sub(r"[-_]{2,}", "-", text)
    text = re.sub(r"[-_=:/：，,;；]+$", "", text)
    text = re.sub(r"^[-_=:/：，,;；]+", "", text)
    text = re.sub(r"\s+", "", text)
    return text or EMPTY_TEXT


def _extract_withholding_purpose(text: str) -> str:
    match = re.search(r"代扣款[（(]扣款用途[:：]([^_，,）)]+)", text)
    if not match:
        return ""
    purpose = match.group(1).strip()
    return f"{purpose}扣款" if purpose else ""
