import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
import pymupdf
from schemas import Extraction, Clause, Evidence
from parser import extract_chunk, AnchoredExtraction, AnchoredClause
from local_model import load_model, predict_hints
from train import run_training


class LocalTrainingTest(unittest.TestCase):
    def test_repair_paraphrase_by_literal_line_selection(self):
        wrong=Extraction(clauses=[Clause(category='신청 자격',summary='학생',
            evidence=[Evidence(page=4,quote='대학생 지원 가능')])],uncertainties=[])
        anchored=AnchoredExtraction(clauses=[AnchoredClause(category='신청 자격',summary='재학생 대상',line_ids=[1])],uncertainties=[])
        ask=Mock(side_effect=[wrong,wrong,anchored])
        result=extract_chunk(ask,{'page':4,'text':'현재 재학생만 신청할 수 있다.\n휴학생은 제외한다.'})
        self.assertEqual(result.clauses[0].evidence[0].quote,'현재 재학생만 신청할 수 있다.')
        self.assertEqual(ask.call_count,3)

    def test_repair_cannot_invent_line_id(self):
        wrong=Extraction(clauses=[Clause(category='신청 자격',summary='학생',evidence=[Evidence(page=1,quote='없는 문장')])],uncertainties=[])
        anchored=AnchoredExtraction(clauses=[AnchoredClause(category='신청 자격',summary='학생',line_ids=[999])],uncertainties=[])
        with self.assertRaises(ValueError):
            extract_chunk(Mock(side_effect=[wrong,wrong,anchored]),{'page':1,'text':'실제 원문'})

    def test_printed_page_number_and_unicode_spacing(self):
        parsed=Extraction(clauses=[Clause(category='신청 자격',summary='학생',
            evidence=[Evidence(page=99,quote='Ａ 재학생만 신청')])],uncertainties=[])
        result=extract_chunk(Mock(return_value=parsed),{'page':4,'text':'A 재학생만\u200b 신청'})
        self.assertEqual(result.clauses[0].evidence[0].page,4)

    def test_actual_local_model_fit_save_load_and_cache(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);dataset=root/'dataset';dataset.mkdir()
            for i in range(5):
                with pymupdf.open() as doc:
                    page=doc.new_page()
                    lines=[]
                    for j in range(6):
                        lines.extend([f'Students apply eligibility university DOC{i} ITEM{j}.',
                                      f'Submit document certificate proof DOC{i} ITEM{j}.'])
                    page.insert_text((35,35),'\n'.join(lines))
                    doc.save(dataset/f'{i}.pdf')
            system=Mock();system.model='mock-teacher';system.usage={}
            def annotate(prompt,payload,schema):
                clauses=[]
                for line in payload['text'].splitlines():
                    category='신청 자격' if 'Students' in line else '제출 서류'
                    clauses.append(Clause(category=category,summary=category,
                        evidence=[Evidence(page=payload['page'],quote=line)]))
                return Extraction(clauses=clauses,uncertainties=[])
            system.ask.side_effect=annotate
            model_path=root/'models'/'clause_classifier.joblib'
            summary=run_training(dataset,system,model_path,root/'training')
            self.assertTrue(model_path.is_file())
            artifact=load_model(model_path)
            self.assertTrue(predict_hints('Students apply university eligibility certificate document.',artifact))
            groups=[set(summary['split'][name]['documents']) for name in ('train','validation','test')]
            self.assertFalse(groups[0]&groups[1] or groups[0]&groups[2] or groups[1]&groups[2])
            calls=system.ask.call_count
            run_training(dataset,system,model_path,root/'training')
            self.assertEqual(system.ask.call_count,calls)
            self.assertIn('silver',summary['label_source'])
