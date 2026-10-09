import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import app as app_module
import jobs.coupon_push_job as coupon_push_job


class PushRegistrationTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            PUSH_MAX_TOKENS_PER_CLIENT=50,
            PUSH_MAX_TOKEN_ROWS=10000,
        )
        with app_module.app.app_context():
            app_module.db.session.remove()
            app_module.PushToken.query.delete()
            app_module.PushEnrollmentReservation.query.delete()
            app_module.CouponSeen.query.delete()
            app_module.db.session.execute(
                app_module.update(app_module.PushEnrollmentGate)
                .where(app_module.PushEnrollmentGate.id == 1)
                .values(generation=0)
            )
            app_module.db.session.commit()

    def _register(self, token, client_ip="203.0.113.10", remote_addr="127.0.0.1"):
        with app_module.app.test_client() as client:
            return client.post(
                "/api/push/register",
                json={"token": token},
                headers={"X-Real-IP": client_ip},
                environ_overrides={"REMOTE_ADDR": remote_addr},
            )

    def _stored_token_count(self):
        with app_module.app.app_context():
            return app_module.PushToken.query.count()

    def test_malformed_and_oversized_inputs_are_rejected_before_verification(self):
        with mock.patch.object(app_module, "_verify_push_token_with_fcm") as verify:
            for payload in ([], {"token": 7}, {"token": " "}, {"token": "bad\ntoken"}, {"token": "x" * 513}):
                with app_module.app.test_client() as client:
                    response = client.post("/api/push/register", json=payload)
                self.assertEqual(response.status_code, 400)

            with app_module.app.test_client() as client:
                response = client.post(
                    "/api/push/register",
                    data='{"token":"' + ("x" * 2500) + '"}',
                    content_type="application/json",
                )
            self.assertEqual(response.status_code, 413)

        verify.assert_not_called()
        self.assertEqual(self._stored_token_count(), 0)

    def test_only_fcm_project_tokens_are_enrolled_and_opaque_values_are_preserved(self):
        with mock.patch.object(app_module, "_verify_push_token_with_fcm", return_value=False):
            rejected = self._register("not-a-project-token")
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self._stored_token_count(), 0)

        token = "opaque:+/=_firebase-token"
        with mock.patch.object(app_module, "_verify_push_token_with_fcm", return_value=True):
            first = self._register(token)
            second = self._register(token)

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.get_json()["created"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.get_json()["created"])
        with app_module.app.app_context():
            row = app_module.PushToken.query.one()
            self.assertEqual(row.token, token)
            self.assertTrue(row.is_enabled)
            self.assertTrue(row.client_ip_hash)

    def test_fcm_project_mismatch_uses_non_delivering_validation(self):
        app_instance = object()
        mismatch = app_module.messaging.SenderIdMismatchError("token is outside this project")
        with (
            mock.patch.object(app_module, "_get_push_fcm_admin_app", return_value=app_instance),
            mock.patch.object(app_module.messaging, "send", side_effect=mismatch) as send,
        ):
            accepted = app_module._verify_push_token_with_fcm("opaque-token")

        self.assertFalse(accepted)
        message = send.call_args.args[0]
        self.assertEqual(message.token, "opaque-token")
        self.assertTrue(send.call_args.kwargs["dry_run"])
        self.assertIs(send.call_args.kwargs["app"], app_instance)

    def test_per_client_quota_is_atomic_for_concurrent_registrations(self):
        app_module.app.config["PUSH_MAX_TOKENS_PER_CLIENT"] = 1
        tokens = [f"opaque-client-token-{index}" for index in range(4)]
        with mock.patch.object(app_module, "_verify_push_token_with_fcm", return_value=True) as verify:
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses = list(pool.map(lambda token: self._register(token), tokens))

        self.assertEqual(sorted(response.status_code for response in responses), [200, 429, 429, 429])
        self.assertEqual(self._stored_token_count(), 1)
        self.assertEqual(verify.call_count, 1)

    def test_global_quota_is_atomic_across_clients(self):
        app_module.app.config["PUSH_MAX_TOKEN_ROWS"] = 1
        inputs = [("opaque-global-a", "203.0.113.11"), ("opaque-global-b", "203.0.113.12")]
        with mock.patch.object(app_module, "_verify_push_token_with_fcm", return_value=True) as verify:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda item: self._register(item[0], item[1]), inputs))

        self.assertEqual(sorted(response.status_code for response in responses), [200, 429])
        self.assertEqual(self._stored_token_count(), 1)
        self.assertEqual(verify.call_count, 1)


    def test_rejected_verification_releases_capacity_reservation(self):
        with mock.patch.object(app_module, "_verify_push_token_with_fcm", return_value=False):
            response = self._register("not-a-project-token")

        self.assertEqual(response.status_code, 400)
        with app_module.app.app_context():
            self.assertEqual(app_module.PushEnrollmentReservation.query.count(), 0)
            self.assertEqual(app_module.PushToken.query.count(), 0)

    def test_full_quota_rejects_before_external_fcm_validation(self):
        app_module.app.config["PUSH_MAX_TOKENS_PER_CLIENT"] = 1
        with mock.patch.object(app_module, "_verify_push_token_with_fcm", return_value=True):
            self.assertEqual(self._register("first-token").status_code, 200)

        with mock.patch.object(app_module, "_verify_push_token_with_fcm") as verify:
            response = self._register("second-token")

        self.assertEqual(response.status_code, 429)
        verify.assert_not_called()


class CouponPushJobTests(unittest.TestCase):
    def setUp(self):
        with app_module.app.app_context():
            app_module.db.session.remove()
            app_module.PushToken.query.delete()
            app_module.PushEnrollmentReservation.query.delete()
            app_module.CouponSeen.query.delete()
            app_module.db.session.commit()

    def _add_tokens(self, tokens, verified=True):
        with app_module.app.app_context():
            for value in tokens:
                app_module.db.session.add(
                    app_module.PushToken(
                        token=value,
                        last_seen=datetime.utcnow(),
                        fcm_verified_at=datetime.utcnow() if verified else None,
                    )
                )
            app_module.db.session.commit()

    def test_job_reads_bounded_pages_and_batches_before_marking_codes_seen(self):
        self._add_tokens(["fcm-a", "fcm-b", "fcm-c"])

        def send_batch(multicast, app=None):
            return SimpleNamespace(
                responses=[SimpleNamespace(success=True) for _ in multicast.tokens]
            )

        with (
            mock.patch.object(coupon_push_job, "_fetch_coupon_codes", return_value=["NEW-CODE"]),
            mock.patch.object(coupon_push_job, "_get_fcm_app", return_value=object()),
            mock.patch.object(
                coupon_push_job.messaging,
                "send_each_for_multicast",
                side_effect=send_batch,
            ) as send,
            mock.patch.object(coupon_push_job, "PUSH_JOB_BATCH_SIZE", 2),
            mock.patch.object(coupon_push_job, "PUSH_JOB_DEADLINE_SECONDS", 30),
        ):
            coupon_push_job.run()

        self.assertEqual(send.call_count, 2)
        self.assertEqual(
            [len(call.args[0].tokens) for call in send.call_args_list],
            [2, 1],
        )
        with app_module.app.app_context():
            self.assertEqual(app_module.CouponSeen.query.count(), 1)
            self.assertTrue(
                all(row.last_push_at for row in app_module.PushToken.query.order_by(app_module.PushToken.id))
            )

    def test_job_validates_legacy_rows_before_delivery(self):
        self._add_tokens(["legacy-valid", "legacy-invalid"], verified=False)
        calls = []

        def send_batch(multicast, dry_run=False, app=None):
            calls.append((list(multicast.tokens), dry_run))
            if dry_run:
                return SimpleNamespace(
                    responses=[
                        SimpleNamespace(success=token == "legacy-valid", exception=(
                            None if token == "legacy-valid" else app_module.messaging.UnregisteredError("gone")
                        ))
                        for token in multicast.tokens
                    ]
                )
            return SimpleNamespace(
                responses=[SimpleNamespace(success=True, exception=None) for _ in multicast.tokens]
            )

        with (
            mock.patch.object(coupon_push_job, "_fetch_coupon_codes", return_value=["NEW-CODE"]),
            mock.patch.object(coupon_push_job, "_get_fcm_app", return_value=object()),
            mock.patch.object(
                coupon_push_job.messaging,
                "send_each_for_multicast",
                side_effect=send_batch,
            ),
        ):
            coupon_push_job.run()

        self.assertEqual(calls[0], (["legacy-valid", "legacy-invalid"], True))
        self.assertEqual(calls[1], (["legacy-valid"], False))
        with app_module.app.app_context():
            rows = {row.token: row for row in app_module.PushToken.query.all()}
            self.assertIsNotNone(rows["legacy-valid"].fcm_verified_at)
            self.assertTrue(rows["legacy-valid"].is_enabled)
            self.assertFalse(rows["legacy-invalid"].is_enabled)
            self.assertEqual(app_module.CouponSeen.query.count(), 1)

    def test_transient_legacy_validation_failure_keeps_codes_pending(self):
        self._add_tokens(["legacy-unavailable"], verified=False)
        with (
            mock.patch.object(coupon_push_job, "_fetch_coupon_codes", return_value=["NEW-CODE"]),
            mock.patch.object(coupon_push_job, "_get_fcm_app", return_value=object()),
            mock.patch.object(
                coupon_push_job.messaging,
                "send_each_for_multicast",
                return_value=SimpleNamespace(
                    responses=[SimpleNamespace(success=False, exception=RuntimeError("temporary"))]
                ),
            ) as send,
        ):
            coupon_push_job.run()

        self.assertTrue(send.call_args.kwargs["dry_run"])
        with app_module.app.app_context():
            row = app_module.PushToken.query.one()
            self.assertIsNone(row.fcm_verified_at)
            self.assertEqual(app_module.CouponSeen.query.count(), 0)

    def test_job_deadline_leaves_codes_pending_for_a_later_run(self):
        self._add_tokens(["fcm-a"])
        with (
            mock.patch.object(coupon_push_job, "_fetch_coupon_codes", return_value=["NEW-CODE"]),
            mock.patch.object(coupon_push_job, "_get_fcm_app", return_value=object()),
            mock.patch.object(coupon_push_job.messaging, "send_each_for_multicast") as send,
            mock.patch.object(coupon_push_job, "PUSH_JOB_DEADLINE_SECONDS", -1),
        ):
            coupon_push_job.run()

        send.assert_not_called()
        with app_module.app.app_context():
            self.assertEqual(app_module.CouponSeen.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
