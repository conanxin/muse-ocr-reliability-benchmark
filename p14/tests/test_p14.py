import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import p14


class P14ProtocolTests(unittest.TestCase):
    def test_manifest_locked_population(self):
        manifest,pages,gold=p14.protocol()
        self.assertEqual(len(pages),20)
        self.assertEqual(len(gold),5)
        self.assertEqual(len(set(pages)),20)
        self.assertEqual(set(gold)-set(pages),set())

    def test_edit_distance(self):
        self.assertEqual(p14.levenshtein('kitten','sitting'),3)
        self.assertEqual(p14.levenshtein('值得研究，','值得研究。'),1)
        self.assertEqual(p14.levenshtein('','abc'),3)

    def test_normalize_preserves_punctuation(self):
        self.assertEqual(p14.normalize('A\n   B。'),'A B。')
        self.assertNotEqual(p14.normalize('A B。'),p14.normalize('A B，'))

    def test_missing_labels_not_measured(self):
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td)
            self.assertEqual(p14.optional_labels(out/'none.jsonl','omissions')['status'],'NOT_MEASURED')
            self.assertEqual(p14.optional_labels(out/'none2.jsonl','ai')['status'],'NOT_MEASURED')

    def test_omission_denominators(self):
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'labels.jsonl'
            path.write_text('\n'.join(json.dumps(x) for x in [
                {'source_verified':True,'detected_by_ocr_quality_gate':True},
                {'source_verified':True,'detected_by_ocr_quality_gate':False},
                {'source_verified':False,'detected_by_ocr_quality_gate':True}
            ]))
            val=p14.optional_labels(path,'omissions')
            self.assertEqual((val['true_positives'],val['false_negatives']),(1,1))
            self.assertEqual(val['recall'],0.5)

    def test_ai_applied_vs_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'labels.jsonl'
            path.write_text('\n'.join(json.dumps(x) for x in [
                {'gold_checked':True,'human_verdict':'correct_applied'},
                {'gold_checked':True,'human_verdict':'miscorrection_applied'},
                {'gold_checked':True,'human_verdict':'proposed_wrong_rejected'}
            ]))
            val=p14.optional_labels(path,'ai')
            self.assertEqual(val['applied_edits_reviewed'],2)
            self.assertEqual(val['miscorrection_rate'],0.5)
            self.assertEqual(val['wrong_proposals_rejected'],1)


if __name__ == '__main__':
    unittest.main()
