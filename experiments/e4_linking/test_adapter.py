import unittest
from adapter import link_observation,WorkOrder


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context={'project_id':'P','block_id':'B','as_of':'2026-10-09T00:00:00+09:00'}
        self.orders=[WorkOrder.from_dict({'project_id':'P','block_id':'B','order_id':'O','part_id':'B-108','revision':1,'valid_from':'2026-10-08T00:00:00+09:00','state':'released','instruction':'synthetic'})]

    def test_invalid_alternative_cannot_disappear_into_match(self) -> None:
        result=link_observation({'candidates':[{'text':'B-108'},{'text':'B 108'}]},self.orders,self.context)
        self.assertEqual(result['status'],'review_required')
        self.assertEqual(result['observed_texts'],['B-108','B 108'])
        self.assertEqual(result['rejected_candidates'][0]['text'],'B 108')

    def test_ambiguity_preserved_even_with_one_order(self) -> None:
        result=link_observation({'candidates':[{'text':'B-108'},{'text':'B-103'}]},self.orders,self.context)
        self.assertEqual(result['status'],'review_required')

    def test_confusion_not_repaired(self) -> None:
        result=link_observation({'candidates':[{'text':'B-1O8'}]},self.orders,self.context)
        self.assertEqual(result['status'],'unmatched')
        self.assertFalse(result['execution_authorized'])

    def test_all_unsupported_preserved(self) -> None:
        result=link_observation({'candidates':[{'text':'부재 ?'}]},self.orders,self.context)
        self.assertEqual(result['status'],'unreadable')
        self.assertEqual(len(result['rejected_candidates']),1)


if __name__=='__main__':unittest.main()
