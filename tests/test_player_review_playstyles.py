import unittest

from werkzeug.datastructures import MultiDict

import app as app_module


class PlayerReviewPlaystyleTests(unittest.TestCase):
    def setUp(self):
        self.field_player = {
            "position": "RW",
            "playStyleSlotMaxLevels": [1, 1],
            "playstyles": [
                {
                    "code": "PLAYSTYLE_TRICKSTER_1",
                    "name": "트릭스터",
                    "imageUrl": "/static/playstyles/PLAYSTYLE_TRICKSTER_1.png",
                }
            ],
        }

    def test_choice_slot_only_exists_for_empty_player_slot(self):
        slots = app_module._build_review_playstyle_choice_slots(self.field_player)

        self.assertEqual(1, len(slots))
        self.assertEqual(2, slots[0]["slotNumber"])
        self.assertTrue(slots[0]["options"])
        self.assertNotIn(
            "PLAYSTYLE_TRICKSTER_1",
            {item["code"] for item in slots[0]["options"]},
        )
        self.assertNotIn("GK", {item["category"] for item in slots[0]["options"]})
        self.assertTrue(all(item["level"] <= 1 for item in slots[0]["options"]))

    def test_no_empty_slot_means_no_review_playstyle_field(self):
        player = dict(self.field_player, playStyleSlotMaxLevels=[1])
        self.assertEqual([], app_module._build_review_playstyle_choice_slots(player))

    def test_selected_playstyle_is_saved_with_slot_and_image(self):
        slots = app_module._build_review_playstyle_choice_slots(self.field_player)
        player = dict(self.field_player, reviewPlaystyleChoiceSlots=slots)
        option = slots[0]["options"][0]

        saved = app_module._review_playstyle_config_from_form(
            player,
            MultiDict({"playstyle_slot_2": option["code"]}),
        )

        self.assertEqual(1, len(saved))
        self.assertEqual(2, saved[0]["slotNumber"])
        self.assertEqual(option["code"], saved[0]["code"])
        self.assertEqual(option["imageUrl"], saved[0]["imageUrl"])

    def test_rejects_playstyle_not_available_for_slot(self):
        slots = app_module._build_review_playstyle_choice_slots(self.field_player)
        player = dict(self.field_player, reviewPlaystyleChoiceSlots=slots)

        with self.assertRaisesRegex(ValueError, "선택할 수 없는"):
            app_module._review_playstyle_config_from_form(
                player,
                MultiDict({"playstyle_slot_2": "PLAYSTYLE_SUPER_RUSH_1"}),
            )

    def test_review_form_shows_selector_and_images_for_empty_slot(self):
        player = app_module._build_review_player_context(22901950)

        with app_module.app.test_request_context("/player/22901950/review/new"):
            html = app_module._render_player_review_form(player, [])

        self.assertIn("추가 플레이스타일", html)
        self.assertIn("장착한 플레이스타일을 선택해주세요.", html)
        self.assertNotIn("이 카드의 빈 플레이스타일 슬롯에 실제로 사용한", html)
        self.assertIn('name="playstyle_slot_2"', html)
        self.assertIn('data-review-playstyle-image', html)
        self.assertIn('body.review-form-page .main-content', html)
        self.assertIn('html[data-theme="dark"] .review-form-page .playstyle-config', html)
        self.assertIn('html[data-theme="dark"] .review-form-page .skill-config', html)
        self.assertIn('grid-template-columns: 42px minmax(0, 1fr)', html)
        self.assertIn('width: 76px', html)

    def test_review_form_hides_selector_when_all_slots_are_filled(self):
        player = app_module._build_review_player_context(22512801)

        with app_module.app.test_request_context("/player/22512801/review/new"):
            html = app_module._render_player_review_form(player, [])

        self.assertNotIn("추가 플레이스타일", html)
        self.assertNotIn('name="playstyle_slot_', html)


if __name__ == "__main__":
    unittest.main()
