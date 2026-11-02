import io
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
from agents import (AgentSystem, Clause, Claim, Debate, Evidence, Extraction,
                    Report, chunks, load_documents, validate_claims, validate_evidence)


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.clause = Clause(category='신청 제외 대상', summary='체납 기업 제외',
                             evidence=[Evidence(page=1, quote='체납 기업은 신청 불가')])
        self.claim = Claim(conclusion='체납 여부 미확인', clause_ids=['C0001'],
                           profile_keys=['체납'], assessment='미확인', response_to='검토')

    def test_fake_citation_rejected(self):
        with self.assertRaises(ValueError):
            validate_evidence(Extraction(clauses=[self.clause], uncertainties=[]), {1: '다른 내용'})

    def test_fake_profile_and_missing_evidence_rejected(self):
        with self.assertRaises(ValueError):
            validate_claims([self.claim], {'C0001'}, {})
        with self.assertRaises(ValueError):
            validate_claims([self.claim.model_copy(update={'clause_ids': []})], {'C0001'}, {'체납': None})

    def test_all_text_covered(self):
        text = '가' * 45000 + '마지막 제외 조항'
        parts = list(chunks({1: text}))
        self.assertIn('마지막 제외 조항', parts[-1]['text'])
        self.assertTrue(all(len(p['text']) <= 12000 for p in parts))

    def test_zip_uses_memory_does_not_extract_paths(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'input.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('../escape.pdf', b'not-real-pdf')
                z.writestr('readme.txt', 'ignore')
            self.assertEqual(load_documents(path), [('../escape.pdf', b'not-real-pdf')])
            self.assertFalse((Path(directory).parent / 'escape.pdf').exists())

    def test_end_to_end_two_rounds_with_mock_api(self):
        debate = Debate(claims=[self.claim], missing_information=['체납 여부 확인'])
        report = Report(status='신청 가능', summary='추가 검토', fatal_disqualifications=[],
                        positive_factors=[], improvements=['체납 증명 확인'], unresolved_questions=[])
        outputs = [Extraction(clauses=[self.clause], uncertainties=[]),
                   debate, debate, debate, debate, report]
        client = Mock()
        client.responses.parse.side_effect = [SimpleNamespace(output_parsed=x,
            usage=SimpleNamespace(input_tokens=10, output_tokens=10)) for x in outputs]
        system = AgentSystem('mock', client)
        result = system.run('공고.pdf', {1: '체납 기업은 신청 불가'}, {'체납': None}, [])
        self.assertEqual(len(result['debate']), 4)
        self.assertEqual(result['report']['status'], '추가 확인 필요')
        self.assertEqual(system.usage['calls'], 6)
        self.assertEqual(client.responses.parse.call_args.kwargs['store'], False)

    def test_confirmed_disqualification_overrides_positive_status(self):
        claim = self.claim.model_copy(update={'assessment': '불충족'})
        system = AgentSystem('mock', Mock())
        system.ask = Mock(side_effect=[Extraction(clauses=[self.clause], uncertainties=[]),
            Debate(claims=[claim], missing_information=[]),
            Debate(claims=[claim], missing_information=[]),
            Report(status='신청 가능', summary='결격', fatal_disqualifications=[claim],
                   positive_factors=[], improvements=[], unresolved_questions=[])])
        result = system.run('공고.pdf', {1:'체납 기업은 신청 불가'}, {'체납':True}, [], 1)
        self.assertEqual(result['report']['status'], '신청 불가')


if __name__ == '__main__':
    unittest.main()
