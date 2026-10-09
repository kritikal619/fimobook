import unittest

from scripts.generate_player_analysis_reference import build_reference


class PlayerAnalysisReferenceTest(unittest.TestCase):
    @staticmethod
    def _player(position, ovr):
        return {
            "position": position,
            "ovr": ovr,
            "ACC": ovr,
            "SPD": ovr,
            "STA": ovr,
        }

    def test_exact_position_radius_and_asymmetric_wingback_cohorts(self):
        players = [
            self._player("ST", 100),
            self._player("ST", 104),
            self._player("CF", 100),
            self._player("CF", 104),
            self._player("LM", 100),
            self._player("LM", 104),
            self._player("RM", 100),
            self._player("RM", 104),
            self._player("LB", 102),
            self._player("LWB", 100),
            self._player("RB", 102),
            self._player("RWB", 100),
        ]

        reference = build_reference(players)

        self.assertEqual(reference["ST"]["100"]["sample"], 1)
        for position in ("CF", "LM", "RM"):
            self.assertEqual(reference[position]["100"]["radius"], 4)
            self.assertEqual(reference[position]["100"]["sample"], 2)

        self.assertEqual(reference["LWB"]["100"]["positions"], ["LWB", "LB"])
        self.assertEqual(reference["LWB"]["100"]["sample"], 2)
        self.assertEqual(reference["LB"]["102"]["positions"], ["LB"])
        self.assertEqual(reference["LB"]["102"]["sample"], 1)

        self.assertEqual(reference["RWB"]["100"]["positions"], ["RWB", "RB"])
        self.assertEqual(reference["RWB"]["100"]["sample"], 2)
        self.assertEqual(reference["RB"]["102"]["positions"], ["RB"])
        self.assertEqual(reference["RB"]["102"]["sample"], 1)


if __name__ == "__main__":
    unittest.main()
