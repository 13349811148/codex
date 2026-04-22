from __future__ import annotations

import unittest

from domain.remark_normalizer import normalize_taobao_remark


class RemarkNormalizerTests(unittest.TestCase):
    def test_removes_order_number_in_parentheses(self) -> None:
        self.assertEqual(
            normalize_taobao_remark("基础软件服务费(4502224875038010343)扣款"),
            "基础软件服务费扣款",
        )

    def test_removes_bare_long_order_number(self) -> None:
        self.assertEqual(
            normalize_taobao_remark("基础软件服务费4502224875038010343扣款"),
            "基础软件服务费扣款",
        )

    def test_preserves_short_business_code(self) -> None:
        self.assertEqual(
            normalize_taobao_remark("百亿补贴软件服务费T62（全渠道）(KY_ITEM)(4502224875038010343)扣款"),
            "百亿补贴软件服务费T62扣款",
        )

    def test_removes_order_marker_with_separator(self) -> None:
        self.assertEqual(
            normalize_taobao_remark("淘工厂技术服务费_订单号2701793460165039390扣款"),
            "淘工厂技术服务费扣款",
        )

    def test_extracts_withholding_purpose(self) -> None:
        self.assertEqual(
            normalize_taobao_remark(
                "代扣款（扣款用途：消费者体验提升计划服务费_订单号2701793460165039390，付款方：湖北庄品健实业有限公司）"
            ),
            "消费者体验提升计划服务费扣款",
        )

    def test_removes_tb_order_marker(self) -> None:
        self.assertEqual(
            normalize_taobao_remark("公益宝贝捐赠=味美乡村图书馆=tb924756926975"),
            "公益宝贝捐赠=味美乡村图书馆",
        )


if __name__ == "__main__":
    unittest.main()
