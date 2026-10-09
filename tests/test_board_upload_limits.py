import io
import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

import app as app_module


class _UploadedFile:
    def __init__(self, filename, data):
        self.filename = filename
        self.stream = io.BytesIO(data)


def _png_bytes(size=(8, 8)):
    output = io.BytesIO()
    Image.new("RGB", size, color="blue").save(output, format="PNG")
    return output.getvalue()


class BoardUploadLimitsTest(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._old_upload_folder = app_module.app.config["UPLOAD_FOLDER"]
        self._old_instance_path = app_module.app.instance_path
        self._old_testing = app_module.app.config.get("TESTING")
        self._old_csrf = app_module.app.config.get("WTF_CSRF_ENABLED")
        app_module.app.config["UPLOAD_FOLDER"] = self._temp_dir.name
        app_module.app.instance_path = self._temp_dir.name
        app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def tearDown(self):
        app_module.app.config["UPLOAD_FOLDER"] = self._old_upload_folder
        app_module.app.instance_path = self._old_instance_path
        app_module.app.config["TESTING"] = self._old_testing
        app_module.app.config["WTF_CSRF_ENABLED"] = self._old_csrf
        self._temp_dir.cleanup()

    def test_valid_image_is_saved_with_server_generated_name(self):
        with patch.object(app_module, "_cleanup_orphaned_board_images"), patch.object(
            app_module,
            "_board_image_storage_usage",
            return_value={"active_bytes": 0, "active_images": 0, "users": {}},
        ):
            filename = app_module._save_uploaded_post_image(
                _UploadedFile("photo.png", _png_bytes()), user_id=7
            )

        self.assertRegex(filename, r"^board_[0-9a-f]{32}\.png$")
        self.assertTrue(os.path.isfile(os.path.join(self._temp_dir.name, filename)))

    def test_rejects_oversized_and_extension_mismatched_images(self):
        old_limit = app_module.BOARD_MAX_IMAGE_BYTES
        app_module.BOARD_MAX_IMAGE_BYTES = len(_png_bytes()) - 1
        try:
            with app_module.app.test_request_context("/board/new"):
                with self.assertRaises(RequestEntityTooLarge):
                    app_module._validated_board_post_image(
                        _UploadedFile("photo.png", _png_bytes())
                    )
        finally:
            app_module.BOARD_MAX_IMAGE_BYTES = old_limit

        with app_module.app.test_request_context("/board/new"):
            with self.assertRaises(BadRequest):
                app_module._validated_board_post_image(
                    _UploadedFile("photo.jpg", _png_bytes())
                )

    def test_account_quota_rejects_before_writing_file(self):
        old_limit = app_module.BOARD_MAX_ACTIVE_IMAGES_PER_USER
        app_module.BOARD_MAX_ACTIVE_IMAGES_PER_USER = 1
        usage = {
            "active_bytes": 0,
            "active_images": 1,
            "users": {7: {"active_bytes": 0, "active_images": 1}},
        }
        try:
            with patch.object(app_module, "_cleanup_orphaned_board_images"), patch.object(
                app_module, "_board_image_storage_usage", return_value=usage
            ):
                with app_module.app.test_request_context("/board/new"):
                    with self.assertRaises(RequestEntityTooLarge):
                        app_module._save_uploaded_post_image(
                            _UploadedFile("photo.png", _png_bytes()), user_id=7
                        )
        finally:
            app_module.BOARD_MAX_ACTIVE_IMAGES_PER_USER = old_limit

        self.assertEqual(os.listdir(self._temp_dir.name), [])

    def test_cleanup_only_removes_unreferenced_files_inside_upload_root(self):
        orphan = os.path.join(self._temp_dir.name, "board_orphan.png")
        with open(orphan, "wb") as image_file:
            image_file.write(b"image")
        with patch.object(app_module, "_post_image_is_referenced", return_value=False):
            self.assertTrue(app_module._remove_post_image_if_unreferenced("board_orphan.png"))
        self.assertFalse(os.path.exists(orphan))

        with open(orphan, "wb") as image_file:
            image_file.write(b"image")
        with patch.object(app_module, "_post_image_is_referenced", return_value=True):
            self.assertTrue(app_module._remove_post_image_if_unreferenced("board_orphan.png"))
        self.assertTrue(os.path.exists(orphan))

        outside = os.path.join(self._temp_dir.name, "outside.png")
        with open(outside, "wb") as image_file:
            image_file.write(b"keep")
        with patch.object(app_module, "_post_image_is_referenced", return_value=False):
            app_module._remove_post_image_if_unreferenced("../outside.png")
        self.assertTrue(os.path.exists(outside))

    def test_orphan_sweep_removes_only_generated_board_image_names(self):
        orphan = os.path.join(self._temp_dir.name, "board_" + "a" * 32 + ".png")
        referenced = os.path.join(self._temp_dir.name, "board_" + "b" * 32 + ".png")
        other = os.path.join(self._temp_dir.name, "manual.png")
        for path in (orphan, referenced, other):
            with open(path, "wb") as image_file:
                image_file.write(b"image")

        with patch.object(
            app_module,
            "_referenced_post_image_filenames",
            return_value={os.path.basename(referenced)},
        ):
            app_module._cleanup_orphaned_board_images()

        self.assertFalse(os.path.exists(orphan))
        self.assertTrue(os.path.exists(referenced))
        self.assertTrue(os.path.exists(other))

    def test_oversized_request_is_rejected_before_login_and_small_control_reaches_login(self):
        old_limit = app_module.BOARD_MAX_REQUEST_BYTES
        app_module.BOARD_MAX_REQUEST_BYTES = 1024
        try:
            with app_module.app.test_client() as client:
                oversized = client.post(
                    "/board/new",
                    data={"title": "x" * 2048, "content": "body"},
                )
                control = client.post(
                    "/board/new",
                    data={"title": "ordinary", "content": "body"},
                )
        finally:
            app_module.BOARD_MAX_REQUEST_BYTES = old_limit

        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(control.status_code, 302)
        self.assertIn("/login", control.headers["Location"])


if __name__ == "__main__":
    unittest.main()
