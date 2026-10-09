import unittest
from pathlib import Path

import app as app_module


class MarketFeeCalculatorTest(unittest.TestCase):
    def test_page_renders_example_and_controls(self):
        response = app_module.app.test_client().get("/market-fee-calculator")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("이적시장 수수료 계산기", html)
        self.assertIn('id="sale-price"', html)
        self.assertIn('id="payback-rate"', html)
        self.assertIn("판매 금액 × 70% + 판매 금액 × 30% × 페이백률", html)
        self.assertIn("8억 3,500만 MP", html)
        self.assertNotIn(" BP", html)

    def test_formula_is_applied_in_template(self):
        template = Path("templates/market_fee_calculator.html").read_text(encoding="utf-8")

        self.assertIn("var baseFee = salePrice * 0.3;", template)
        self.assertIn("var paybackAmount = baseFee * (paybackRate / 100);", template)
        self.assertIn("var netAmount = salePrice - actualFee;", template)
        self.assertIn('rateFormatter.format(effectiveRate) + "%"', template)


if __name__ == "__main__":
    unittest.main()
