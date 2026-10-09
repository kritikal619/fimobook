import re
import unittest
from unittest.mock import call, patch

import app as app_module
import seed_clanworldcup as seed_module


class FakeSnapshot:
    def __init__(self, reference):
        self.reference = reference
        self.id = reference.id
        self.exists = reference.data is not None

    def to_dict(self):
        return dict(self.reference.data or {})


class FakeDocument:
    def __init__(self, document_id):
        self.id = str(document_id)
        self.data = None
        self.children = {}

    def collection(self, name):
        if name not in self.children:
            self.children[name] = FakeCollection()
        return self.children[name]

    def get(self):
        return FakeSnapshot(self)

    def set(self, data, merge=False):
        if merge and self.data is not None:
            self.data.update(data)
        else:
            self.data = dict(data)


class FakeCollection:
    def __init__(self):
        self.documents = {}

    def document(self, document_id):
        document_id = str(document_id)
        if document_id not in self.documents:
            self.documents[document_id] = FakeDocument(document_id)
        return self.documents[document_id]

    def stream(self):
        return [FakeSnapshot(doc) for doc in self.documents.values() if doc.data is not None]


class FakeBatch:
    def __init__(self):
        self.operations = []

    def set(self, reference, data):
        self.operations.append(("set", reference, dict(data)))

    def update(self, reference, data):
        self.operations.append(("update", reference, dict(data)))

    def commit(self):
        if len(self.operations) > 500:
            raise AssertionError("Firestore batch exceeded its 500-write limit")
        for operation, reference, data in self.operations:
            if operation == "set":
                reference.data = data
            elif reference.data is not None:
                reference.data.update(data)
        self.operations.clear()


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    def batch(self):
        return FakeBatch()


class ClanworldcupSeedSecurityTest(unittest.TestCase):
    def test_generator_retries_existing_and_duplicate_values(self):
        values = iter(["prior", "member-one", "member-one", "member-two", "member-three", "member-four", "member-five", "admin"])
        with patch.object(seed_module.secrets, "token_urlsafe", side_effect=lambda _: next(values)) as generator:
            codes = seed_module.build_member_codes([{"clanId": "clan01"}], {"CWC-prior"})

        generated_values = [record["code"] for record in codes]
        self.assertEqual(generator.call_count, 8)
        self.assertEqual(len(generated_values), len(set(generated_values)))
        self.assertNotIn("CWC-prior", generated_values)

    def test_codes_are_random_and_reseeding_revokes_all_previous_codes(self):
        clans = [{"clanId": "clan01"}, {"clanId": "clan02"}]
        with patch.object(seed_module.secrets, "token_urlsafe", wraps=seed_module.secrets.token_urlsafe) as generator:
            generated = seed_module.build_member_codes(clans, {"known-old-code"})

        generated_values = [record["code"] for record in generated]
        self.assertEqual(generator.call_count, 11)
        generator.assert_has_calls([call(32)] * 11)
        self.assertEqual(len(generated_values), len(set(generated_values)))
        self.assertTrue(all(re.fullmatch(r"CWC-[A-Za-z0-9_-]{43}", value) for value in generated_values))
        self.assertNotIn("known-old-code", generated_values)
        self.assertEqual(generated[-1]["clanId"], "admin")
        self.assertTrue(generated[-1]["admin"])

        firestore = FakeFirestore()
        base = firestore.collection("tournaments").document("clanworldcup3")
        codes_ref = base.collection("memberCodes")
        legacy_member = "CWC-CLAN01-M1"
        legacy_admin = "known-fixed-admin-code"
        for code, data in (
            (legacy_member, {"code": legacy_member, "clanId": "clan01", "enabled": True}),
            (legacy_admin, {"code": legacy_admin, "clanId": "admin", "enabled": True, "admin": True}),
        ):
            codes_ref.document(code).set(data)
        for index in range(500):
            code = f"old-code-{index}"
            codes_ref.document(code).set({"code": code, "enabled": True})

        seed_module.seed(firestore)
        first_docs = {snap.id: snap.to_dict() for snap in codes_ref.stream()}
        self.assertTrue(all(not first_docs[code]["enabled"] for code in [legacy_member, legacy_admin]))
        self.assertTrue(all(not first_docs[f"old-code-{index}"]["enabled"] for index in range(500)))
        first_active = {code: data for code, data in first_docs.items() if data.get("enabled")}
        self.assertEqual(len(first_active), 161)
        first_admin_code = next(code for code, data in first_active.items() if data.get("admin"))
        self.assertEqual(len(first_active), len({data["code"] for data in first_active.values()}))

        seed_module.seed(firestore)
        second_docs = {snap.id: snap.to_dict() for snap in codes_ref.stream()}
        self.assertTrue(all(not second_docs[code]["enabled"] for code in first_active))
        second_active = {code: data for code, data in second_docs.items() if data.get("enabled")}
        second_admin_code = next(code for code, data in second_active.items() if data.get("admin"))
        second_member_code = next(code for code, data in second_active.items() if data.get("clanId") != "admin")
        self.assertEqual(len(second_active), 161)
        self.assertNotEqual(first_admin_code, second_admin_code)

        with patch.object(app_module, "_fs_base", return_value=base):
            self.assertIsNone(app_module._verify_member_code(legacy_member))
            self.assertIsNone(app_module._verify_member_code(legacy_admin))
            self.assertIsNone(app_module._verify_member_code(first_admin_code))
            self.assertTrue(app_module._verify_member_code(second_admin_code)["admin"])
            self.assertTrue(app_module._verify_member_code(second_member_code)["clanId"])

        with patch.object(app_module, "fs", object()), patch.object(
            app_module, "_fs_base", return_value=base
        ), patch.object(app_module, "_recalc_standings") as recalculate:
            denied = app_module.app.test_client().post(
                "/clanworldcup/api/standings/recalc", json={"code": first_admin_code}
            )
        self.assertEqual(denied.status_code, 403)
        recalculate.assert_not_called()

        with patch.object(app_module, "fs", object()), patch.object(
            app_module, "_fs_base", return_value=base
        ), patch.object(app_module, "_recalc_standings", return_value={"groups": ["A"]}), patch.object(
            app_module, "_sync_knockout_bracket"
        ):
            accepted = app_module.app.test_client().post(
                "/clanworldcup/api/standings/recalc", json={"code": second_admin_code}
            )
        self.assertEqual(accepted.status_code, 200)


if __name__ == "__main__":
    unittest.main()
