from __future__ import annotations


def _to_number(value: str) -> float:
    text = (value or "").strip().replace(",", "")
    if not text:
        return 0.0
    return float(text)


def normalize_amount(income: str, expense: str) -> float:
    income_value = _to_number(income)
    expense_value = _to_number(expense)

    income_has_value = abs(income_value) > 0
    expense_has_value = abs(expense_value) > 0

    if income_has_value and expense_has_value:
        raise ValueError("收入和支出同时存在有效金额")
    if not income_has_value and not expense_has_value:
        raise ValueError("收入和支出同时为空或为0")

    if income_has_value:
        return abs(income_value)
    return expense_value if expense_value < 0 else -expense_value
