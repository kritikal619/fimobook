import unittest
from unittest.mock import patch

import app as app_module


class PlaystyleSlotTests(unittest.TestCase):
    def test_builds_empty_slot_when_capacity_exceeds_equipped_playstyles(self):
        equipped = [{"code": "PLAYSTYLE_TRICKSTER_1", "name": "트릭스터"}]
        player = {"playStyleSlotMaxLevels": [1, 1]}

        with patch.object(app_module, "_extract_player_playstyles", return_value=equipped):
            slots = app_module._build_player_playstyle_slots(player)

        self.assertEqual(2, len(slots))
        self.assertFalse(slots[0]["isEmpty"])
        self.assertEqual("트릭스터", slots[0]["name"])
        self.assertTrue(slots[1]["isEmpty"])
        self.assertEqual(2, slots[1]["slotNumber"])

    def test_no_capacity_and_no_playstyles_means_no_slots(self):
        with patch.object(app_module, "_extract_player_playstyles", return_value=[]):
            slots = app_module._build_player_playstyle_slots(
                {"playStyleSlotMaxLevels": []}
            )

        self.assertEqual([], slots)

    def test_preserves_playstyle_when_slot_metadata_is_missing(self):
        equipped = [{"code": "PLAYSTYLE_TRICKSTER_1", "name": "트릭스터"}]

        with patch.object(app_module, "_extract_player_playstyles", return_value=equipped):
            slots = app_module._build_player_playstyle_slots({})

        self.assertEqual(1, len(slots))
        self.assertFalse(slots[0]["isEmpty"])
        self.assertIsNone(slots[0]["maxLevel"])


if __name__ == "__main__":
    unittest.main()
