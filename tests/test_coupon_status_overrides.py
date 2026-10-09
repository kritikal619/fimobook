import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class CouponStatusOverridesTest(unittest.TestCase):
    def test_manual_unavailable_status_overrides_future_expiration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            override_path = Path(temp_dir) / "coupon_status_overrides.json"
            with patch.object(app_module, "COUPON_STATUS_OVERRIDES_FILE", str(override_path)):
                app_module._set_coupon_status_override("future-code", "unavailable")
                coupons = app_module._prepare_coupons(
                    [{"code": "FUTURE-CODE", "expires": "2099-12-31"}]
                )

            self.assertTrue(coupons[0]["boolExpires"])
            self.assertEqual(coupons[0]["manualStatus"], "unavailable")
            self.assertTrue(coupons[0]["statusOverridden"])

    def test_auto_status_removes_saved_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            override_path = Path(temp_dir) / "coupon_status_overrides.json"
            override_path.write_text(
                json.dumps({"SAMPLE": "unavailable"}),
                encoding="utf-8",
            )
            with patch.object(app_module, "COUPON_STATUS_OVERRIDES_FILE", str(override_path)):
                app_module._set_coupon_status_override("sample", "auto")
                coupons = app_module._prepare_coupons(
                    [{"code": "SAMPLE", "expires": "2099-12-31"}]
                )

            self.assertFalse(coupons[0]["boolExpires"])
            self.assertEqual(coupons[0]["manualStatus"], "auto")
            self.assertEqual(json.loads(override_path.read_text()), {})

    def test_available_status_can_restore_a_source_expired_coupon(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            override_path = Path(temp_dir) / "coupon_status_overrides.json"
            with patch.object(app_module, "COUPON_STATUS_OVERRIDES_FILE", str(override_path)):
                app_module._set_coupon_status_override("old-code", "available")
                coupons = app_module._prepare_coupons(
                    [{"code": "OLD-CODE", "expires": "2020-01-01"}]
                )

            self.assertFalse(coupons[0]["boolExpires"])
            self.assertEqual(coupons[0]["manualStatus"], "available")


if __name__ == "__main__":
    unittest.main()
