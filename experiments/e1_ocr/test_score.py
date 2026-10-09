"""측정이 유리하게 틀어지지 않는지 작은 정답 사례로 확인한다."""

import unittest
from score import assign, distance, iou, normalize, score_text


class ScoringTests(unittest.TestCase):
    def test_edit_distance_known_cases(self) -> None:
        for a, b, expected in [("", "ABC", 3), ("ABC", "", 3), ("kitten", "sitting", 3),
                               ("B-108", "B-1O8", 1), ("same", "same", 0)]:
            self.assertEqual(distance(a, b), expected)

    def test_no_silent_character_repair(self) -> None:
        self.assertEqual(normalize(" b1Sb-10 "), "B1SB-10")
        self.assertNotEqual(normalize("B 10"), normalize("B10"))
        self.assertNotEqual(normalize("B1O"), normalize("B10"))

    def test_missing_prediction_counts_all_characters(self) -> None:
        result = score_text("B-108", None)
        self.assertEqual(result["edits"], 5)
        self.assertFalse(result["normalized_exact"])

    def test_one_prediction_cannot_satisfy_two_labels(self) -> None:
        obs = [{"bbox": [0, 0, 1, 1]}]
        self.assertEqual(len(assign([[0, 0, 1, 1], [0, 0, 1, 1]], obs)), 1)

    def test_geometry_not_transcription_drives_matching(self) -> None:
        obs = [{"bbox": [0, 0, .4, .4], "candidates": [{"text": "WRONG"}]},
               {"bbox": [.6, .6, 1, 1], "candidates": [{"text": "RIGHT"}]}]
        self.assertEqual(assign([[0, 0, .4, .4]], obs), {0: 0})
        self.assertEqual(iou([0, 0, 1, 1], [0, 0, 1, 1]), 1)
        self.assertEqual(iou([0, 0, .4, .4], [.6, .6, 1, 1]), 0)

    def test_top3_does_not_replace_top1(self) -> None:
        obs = {"candidates": [{"text": "B-1O8"}, {"text": "B-108"}]}
        result = score_text("B-108", obs)
        self.assertTrue(result["top3_exact"])
        self.assertFalse(result["normalized_exact"])

    def test_insertions_can_exceed_reference_length(self) -> None:
        result = score_text("A", {"candidates": [{"text": "ABCD"}]})
        self.assertGreater(result["edits"], result["characters"])


if __name__ == "__main__":
    unittest.main()
