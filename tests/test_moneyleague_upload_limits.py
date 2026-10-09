import copy
import io
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from PIL import Image

import app as app_module


class _Snapshot:
    def __init__(self, data):
        self._data = copy.deepcopy(data)
        self.exists = data is not None

    def to_dict(self):
        return copy.deepcopy(self._data)


class _QuotaReference:
    def __init__(self, data):
        self.data = copy.deepcopy(data)

    def get(self, transaction=None):
        return _Snapshot(self.data)

    def set(self, data, merge=False):
        self.data = {**(self.data or {}), **copy.deepcopy(data)} if merge else copy.deepcopy(data)


class _QuotaCollection:
    def __init__(self, reference):
        self.reference = reference

    def document(self, _document_id):
        return self.reference


class _Transaction:
    def set(self, reference, data, merge=False):
        reference.set(data, merge=merge)


class _FakeFirestore:
    def __init__(self, quota_data):
        self.quota_reference = _QuotaReference(quota_data)

    def collection(self, _collection_name):
        return _QuotaCollection(self.quota_reference)

    def transaction(self):
        return _Transaction()


class _UploadedFile:
    def __init__(self, filename, data):
        self.filename = filename
        self.stream = io.BytesIO(data)


def _png_bytes(size=(8, 8)):
    output = io.BytesIO()
    Image.new("RGB", size, color="blue").save(output, format="PNG")
    return output.getvalue()


class MoneyLeagueUploadLimitsTest(unittest.TestCase):
    def test_screenshot_validation_checks_signature_and_decoded_dimensions(self):
        valid = app_module._validated_moneyleague_screenshot(
            _UploadedFile("clan.png", _png_bytes())
        )
        mismatched_signature = app_module._validated_moneyleague_screenshot(
            _UploadedFile("clan.jpg", _png_bytes())
        )
        old_pixel_limit = app_module.MONEYLEAGUE_MAX_IMAGE_PIXELS
        app_module.MONEYLEAGUE_MAX_IMAGE_PIXELS = 64
        try:
            excessive_dimensions = app_module._validated_moneyleague_screenshot(
                _UploadedFile("clan.png", _png_bytes((9, 9)))
            )
        finally:
            app_module.MONEYLEAGUE_MAX_IMAGE_PIXELS = old_pixel_limit

        self.assertIsNotNone(valid)
        self.assertIsNone(mismatched_signature)
        self.assertIsNone(excessive_dimensions)

    def test_screenshot_validation_rejects_oversized_encoded_file(self):
        old_limit = app_module.app.config["MAX_SCREENSHOT_BYTES"]
        app_module.app.config["MAX_SCREENSHOT_BYTES"] = 64
        try:
            result = app_module._validated_moneyleague_screenshot(
                _UploadedFile("large.png", b"x" * 65)
            )
        finally:
            app_module.app.config["MAX_SCREENSHOT_BYTES"] = old_limit

        self.assertIsNone(result)

    def test_screenshot_cleanup_rejects_untrusted_paths_and_removes_owned_file(self):
        old_upload_folder = app_module.app.config["UPLOAD_FOLDER"]
        try:
            with tempfile.TemporaryDirectory() as upload_folder:
                app_module.app.config["UPLOAD_FOLDER"] = upload_folder
                filename = "mreg_1760000000_0123abcd.png"
                relative_path = f"uploads/moneyleague_registrations/{filename}"
                directory = os.path.join(upload_folder, "moneyleague_registrations")
                os.makedirs(directory)
                file_path = os.path.join(directory, filename)
                with open(file_path, "wb") as screenshot:
                    screenshot.write(b"image")

                size, removed = app_module._remove_moneyleague_screenshot(relative_path)
                rejected = app_module._moneyleague_screenshot_file_path(
                    "uploads/moneyleague_registrations/../../outside.png"
                )

                self.assertEqual(size, 5)
                self.assertTrue(removed)
                self.assertFalse(os.path.exists(file_path))
                self.assertIsNone(rejected)
        finally:
            app_module.app.config["UPLOAD_FOLDER"] = old_upload_folder


    def test_comment_deletion_releases_active_storage_but_not_lifetime_writes(self):
        quota = {
            "active_registrations": 0,
            "active_image_bytes": 0,
            "active_comments": 0,
            "active_comment_bytes": 0,
            "total_comment_writes": 0,
            "quota_day": datetime.utcnow().date().isoformat(),
            "daily_write_count": 0,
            "daily_clients": {},
        }
        fake_firestore = _FakeFirestore(quota)
        old_total_limit = app_module.MONEYLEAGUE_MAX_TOTAL_COMMENT_WRITES
        app_module.MONEYLEAGUE_MAX_TOTAL_COMMENT_WRITES = 1
        try:
            with patch.object(app_module, "fs", fake_firestore), patch.object(
                app_module.firestore, "transactional", lambda callback: callback
            ):
                self.assertEqual(
                    app_module._reserve_moneyleague_storage("comment", 600, "b" * 64),
                    "ok",
                )
                app_module._adjust_moneyleague_storage(
                    "comment", count_delta=-1, bytes_delta=-600
                )
                second_write = app_module._reserve_moneyleague_storage(
                    "comment", 600, "d" * 64
                )
        finally:
            app_module.MONEYLEAGUE_MAX_TOTAL_COMMENT_WRITES = old_total_limit

        self.assertEqual(fake_firestore.quota_reference.data["active_comments"], 0)
        self.assertEqual(fake_firestore.quota_reference.data["active_comment_bytes"], 0)
        self.assertEqual(fake_firestore.quota_reference.data["total_comment_writes"], 1)
        self.assertEqual(second_write, "global_limit")

    def test_form_only_edit_uses_daily_write_quota_without_image_storage(self):
        quota = {
            "active_registrations": 1,
            "active_image_bytes": 800,
            "active_comments": 2,
            "active_comment_bytes": 900,
            "total_comment_writes": 2,
            "quota_day": datetime.utcnow().date().isoformat(),
            "daily_write_count": 0,
            "daily_clients": {},
        }
        fake_firestore = _FakeFirestore(quota)
        with patch.object(app_module, "fs", fake_firestore), patch.object(
            app_module.firestore, "transactional", lambda callback: callback
        ):
            result = app_module._reserve_moneyleague_storage("edit", 1200, "c" * 64)

        self.assertEqual(result, "ok")
        self.assertEqual(fake_firestore.quota_reference.data["daily_write_count"], 1)
        self.assertEqual(fake_firestore.quota_reference.data["active_registrations"], 1)
        self.assertEqual(fake_firestore.quota_reference.data["active_image_bytes"], 800)
        self.assertEqual(fake_firestore.quota_reference.data["active_comments"], 2)

    def test_quota_reservation_enforces_per_client_daily_cap(self):
        quota = {
            "active_registrations": 0,
            "active_image_bytes": 0,
            "active_comments": 0,
            "active_comment_bytes": 0,
            "total_comment_writes": 0,
            "quota_day": datetime.utcnow().date().isoformat(),
            "daily_write_count": 0,
            "daily_clients": {},
        }
        fake_firestore = _FakeFirestore(quota)
        old_client_limit = app_module.MONEYLEAGUE_MAX_DAILY_CLIENT_WRITES
        app_module.MONEYLEAGUE_MAX_DAILY_CLIENT_WRITES = 1
        try:
            with patch.object(app_module, "fs", fake_firestore), patch.object(
                app_module.firestore, "transactional", lambda callback: callback
            ):
                first = app_module._reserve_moneyleague_storage(
                    "registration", 10, "a" * 64, new_registration=True
                )
                second = app_module._reserve_moneyleague_storage(
                    "registration", 10, "a" * 64, new_registration=True
                )
        finally:
            app_module.MONEYLEAGUE_MAX_DAILY_CLIENT_WRITES = old_client_limit

        self.assertEqual(first, "ok")
        self.assertEqual(second, "client_limit")
        self.assertEqual(fake_firestore.quota_reference.data["active_registrations"], 1)
        self.assertEqual(fake_firestore.quota_reference.data["active_image_bytes"], 10)
