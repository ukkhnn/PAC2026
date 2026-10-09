import unittest
from rotation import rotate_box, merge


class RotationTests(unittest.TestCase):
    def test_inverse_all_angles(self) -> None:
        box = [.1, .2, .4, .7]
        for angle in [0, 90, 180, 270]:
            recovered = rotate_box(rotate_box(box, angle), (360-angle)%360)
            for a,b in zip(box,recovered): self.assertAlmostEqual(a,b)

    def test_expected_corner(self) -> None:
        self.assertEqual(rotate_box([0,0,.5,.25],90),[0,.5,.25,1])

    def test_candidates_preserved_and_deduplicated(self) -> None:
        box=[.1,.2,.5,.6]
        rotations=[{"angle":0,"observations":[{"bbox":box,"candidates":[{"text":"BAD","confidence":1}]}]},
                   {"angle":90,"observations":[{"bbox":rotate_box(box,90),"candidates":[{"text":"GOOD","confidence":1},{"text":"bad","confidence":.5}]}]}]
        result=merge(rotations)
        self.assertEqual(len(result),1)
        self.assertEqual([c['text'] for c in result[0]['candidates']],['BAD','GOOD'])

    def test_distant_regions_stay_separate(self) -> None:
        result=merge([{"angle":0,"observations":[{"bbox":b,"candidates":[{"text":"A","confidence":1}]} for b in [[0,0,.1,.1],[.9,.9,1,1]]]}])
        self.assertEqual(len(result),2)


if __name__ == '__main__': unittest.main()
