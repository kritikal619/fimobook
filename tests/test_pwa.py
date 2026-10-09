import json
import unittest
from pathlib import Path

import app as app_module


class PwaTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = app_module.app.test_client()

    def test_web_manifest_is_installable(self):
        response = self.client.get("/manifest.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/manifest+json")

        manifest = json.loads(response.data)
        self.assertEqual(manifest["id"], "/")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual({icon["purpose"] for icon in manifest["icons"]}, {"any", "maskable"})
        self.assertTrue(any(icon["sizes"] == "512x512" for icon in manifest["icons"]))
        maskable_icons = [icon for icon in manifest["icons"] if icon["purpose"] == "maskable"]
        self.assertTrue(all("?v=" in icon["src"] for icon in maskable_icons))

        icon_dir = Path(app_module.app.root_path) / "static" / "icons"
        self.assertNotEqual(
            (icon_dir / "pwa-icon-512.png").read_bytes(),
            (icon_dir / "pwa-maskable-512.png").read_bytes(),
        )

    def test_android_adaptive_icon_uses_safe_foreground(self):
        project_root = Path(app_module.app.root_path)
        adaptive_icon = (
            project_root
            / "android"
            / "app"
            / "src"
            / "main"
            / "res"
            / "mipmap-anydpi-v26"
            / "ic_launcher.xml"
        ).read_text(encoding="utf-8")

        self.assertIn('@drawable/ic_launcher_foreground', adaptive_icon)
        self.assertNotIn('@mipmap/ic_maskable', adaptive_icon)

    def test_digital_asset_links_matches_android_package(self):
        response = self.client.get("/.well-known/assetlinks.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")

        statements = json.loads(response.data)
        target = statements[0]["target"]
        self.assertEqual(target["package_name"], "info.fcbook.app")
        self.assertTrue(target["sha256_cert_fingerprints"])

    def test_main_layout_registers_service_worker(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/static/js/pwa.js", response.data)

    def test_service_worker_has_offline_fallback(self):
        response = self.client.get("/firebase-messaging-sw.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Service-Worker-Allowed"], "/")
        self.assertIn(b"/static/offline.html", response.data)


if __name__ == "__main__":
    unittest.main()
