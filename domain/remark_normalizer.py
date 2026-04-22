from __future__ import annotations

import re


EMPTY_TEXT = "[空]"
ORDER_ID_MIN_LENGTH = 10
SEPARATOR_CHARS = r"[-_=:：，,;；\s]"
OPEN_BRACKETS = r"[({（【\[]"
CLOSE_BRACKETS = r"[)}）】\]]"
TRIM_CHARS = r"[-_=:/：，,;；{}()\[\]（）【】]"


def normalize_taobao_remark(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return EMPTY_TEXT

    extracted = _extract_withholding_purpose(text)
    if extracted:
        text = extracted

    text = re.sub(r"(?:（全渠道）|\(全渠道\))", "", text)
    text = re.sub(r"(?:（KY_ITEM）|\(KY_ITEM\))", "", text)
    text = re.sub(r"[（(][^（）()]*[）)]", "", text)

    text = _remove_order_id_fragments(text)
    text = re.sub(r"=tb\d+", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"{SEPARATOR_CHARS}*\d{{{ORDER_ID_MIN_LENGTH},}}{SEPARATOR_CHARS}*", "", text)

    text = re.sub(OPEN_BRACKETS + r"\s*" + CLOSE_BRACKETS, "", text)
    text = _tidy_tail_keywords(text)
    text = re.sub(r"[-_]{2,}", "-", text)
    text = re.sub(rf"{TRIM_CHARS}+$", "", text)
    text = re.sub(rf"^{TRIM_CHARS}+", "", text)
    text = re.sub(r"\s+", "", text)
    return text or EMPTY_TEXT


def _remove_order_id_fragments(text: str) -> str:
    id_token = rf"[A-Za-z0-9_-]{{{ORDER_ID_MIN_LENGTH},}}"
    order_marker = r"(?:关联|业务基础|业务|商户)?订单号"

    # Remove both well-formed "(订单号:123...)" fragments and malformed
    # "(订单号:123..." fragments while preserving meaningful suffixes like "扣款".
    text = re.sub(
        OPEN_BRACKETS + r"?\s*" + order_marker + r"\s*[:：=]?\s*" + id_token + r"\s*" + CLOSE_BRACKETS + r"?",
        "",
        text,
    )

    # Some statements wrap the long order id directly in braces without a label.
    text = re.sub(
        OPEN_BRACKETS + r"\s*" + id_token + r"\s*" + CLOSE_BRACKETS,
        "",
        text,
    )
    return text


def _tidy_tail_keywords(text: str) -> str:
    text = re.sub(r"[_-]+(?=(扣款|退款))", "", text)
    text = re.sub(r"(扣款){2,}", "扣款", text)
    text = re.sub(r"(退款){2,}", "退款", text)
    return text


def _extract_withholding_purpose(text: str) -> str:
    match = re.search(r"代扣款[（(]扣款用途[:：]([^_，,）)]+)", text)
    if not match:
        return ""
    purpose = match.group(1).strip()
    return f"{purpose}扣款" if purpose else ""
