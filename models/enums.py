from enum import Enum


class MajorCategory(str, Enum):
    CASH_IN = "资金到账"
    STORE_COST = "店铺费用"
    AD_COST = "广告费"
    DEPOSIT = "保证金"
    WITHDRAWAL = "资金提现"
    IGNORE = "忽略"
