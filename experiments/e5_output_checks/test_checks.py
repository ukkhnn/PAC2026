import unittest
from check_output import check_output


class OutputTests(unittest.TestCase):
    def test_invented_source_is_not_accepted(self) -> None:
        self.assertEqual(check_output('{"answer":"value","sources":["D9"]}',['D1'])['reason'],'source_not_provided')

    def test_fence_not_silently_repaired(self) -> None:
        text='```json\n{"answer":"value","sources":["D1"]}\n```'
        result=check_output(text,['D1'])
        self.assertEqual(result['status'],'review_required');self.assertEqual(result['raw_output'],text)

    def test_unknown_and_semantic_boundary(self) -> None:
        self.assertEqual(check_output('{"answer":"UNKNOWN","sources":[]}',[])['status'],'abstained')
        result=check_output('{"answer":"unsupported claim","sources":["D1"]}',['D1'])
        self.assertEqual(result['status'],'candidate');self.assertFalse(result['semantic_verified']);self.assertFalse(result['execution_authorized'])

    def test_array_and_missing_evidence(self) -> None:
        self.assertEqual(check_output('[]',[])['reason'],'invalid_schema')
        self.assertEqual(check_output('{"answer":"value","sources":[]}',[])['reason'],'missing_evidence')


if __name__=='__main__':unittest.main()
