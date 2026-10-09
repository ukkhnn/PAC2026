import unittest
from retrieve import retrieve


class RetrieveTests(unittest.TestCase):
    def test_unique_number_and_absent_terms(self) -> None:
        corpus=[{'id':'A','title':'Process','text':'135 means MAG.'},{'id':'B','title':'Location','text':'The symbol tail.'}]
        self.assertEqual([r['id'] for r in retrieve('135',corpus)],['A'])
        self.assertEqual(retrieve('unseenword',corpus),[])

    def test_order_stable_for_ties(self) -> None:
        corpus=[{'id':'B','title':'same','text':'weld'},{'id':'A','title':'same','text':'weld'}]
        self.assertEqual([r['id'] for r in retrieve('weld',corpus)],['A','B'])


if __name__=='__main__': unittest.main()
