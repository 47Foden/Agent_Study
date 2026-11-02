import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest
from knowledge import build, load_index, search
from train_parser import init_labels, prepare, start_job
from evaluate_parser import evaluate as evaluate_extraction
from check_api import check
from settings import ServerConfig
from schemas import Extraction, Clause, Evidence
from test_pdf_ocr import sample_pdf


def embedding_response(texts):
    return SimpleNamespace(data=[SimpleNamespace(index=i,embedding=[1.0,0.5]) for i,t in enumerate(texts)],
                           usage=SimpleNamespace(total_tokens=2))


class DatasetTrainingTest(unittest.TestCase):
    def test_build_cache_and_source_scoped_retrieval(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            dataset=root/'dataset';dataset.mkdir()
            (dataset/'notice.pdf').write_bytes(sample_pdf())
            system=Mock();system.progress=Mock();system.usage={}
            system.client.embeddings.create.side_effect=lambda **kw:embedding_response(kw['input'])
            index=build(dataset,system,root/'index.json')
            calls=system.client.embeddings.create.call_count
            build(dataset,system,root/'index.json')
            self.assertEqual(system.client.embeddings.create.call_count,calls)
            hits,tokens=search(index,'student',system.client,index['documents'][0]['sha256'])
            self.assertEqual(hits[0]['page'],1)
            self.assertEqual(hits[0]['source'],'notice.pdf')
            self.assertEqual(search(index,'student',system.client,'nonexistent')[0],[])

    def test_document_groups_never_overlap(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);labels=root/'labels.jsonl'
            index={'documents':[{'name':f'{i}.pdf','sha256':str(i),'pages':{'1':f'students may apply {i}'}} for i in range(5)]}
            init_labels(index,labels)
            with self.assertRaises(ValueError):prepare(labels,root/'out')
            rows=[json.loads(line) for line in labels.read_text().splitlines()]
            for row in rows:
                row['reviewed']=True
                row['expected_extraction']={'clauses':[{'category':'신청 자격','summary':'학생 대상',
                    'evidence':[{'page':1,'quote':row['text']}]}],'uncertainties':[]}
            labels.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
            summary=prepare(labels,root/'out')
            groups=[set(summary[k]['document_hashes']) for k in ('train','validation','test')]
            self.assertFalse(groups[0] & groups[1] or groups[1]&groups[2] or groups[0]&groups[2])
            self.assertEqual(sum(s['examples'] for s in summary.values()),5)

    def test_parser_metrics_perfect_and_wrong(self):
        expected=Extraction(clauses=[Clause(category='신청 자격',summary='학생',
                            evidence=[Evidence(page=1,quote='학생만 신청')])],uncertainties=[])
        row={'messages':[{}, {'content':json.dumps({'page':1,'text':'학생만 신청'})},
                         {'content':expected.model_dump_json()}]}
        system=Mock();system.ask.return_value=expected;system.parser_model='mock';system.usage={}
        self.assertEqual(evaluate_extraction([row],system)['f1'],1.0)
        system.ask.return_value=Extraction(clauses=[],uncertainties=[])
        self.assertEqual(evaluate_extraction([row],system)['recall'],0.0)

    def test_api_check_never_returns_key(self):
        client=Mock();client.responses.create.return_value.output_text='OK'
        message=check(ServerConfig(api_key='test-secret'),client,True)
        self.assertNotIn('test-secret',message)
        client.embeddings.create.assert_called_once()

    def test_indexed_dataset_appears_in_web(self):
        index={'version':1,'embedding_model':'mock','documents':[{
            'name':'registered.pdf','sha256':'hash','pages':{'1':'Students may apply to this call.'},
            'warnings':[],'chunks':[]} ]}
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'))
        app.secrets['OPENAI_API_KEY']='test-not-real'
        with patch('knowledge.load_index',return_value=index):
            app.run()
            app.radio[0].set_value('등록된 데이터셋').run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.session_state['prepared'][0]['name'],'registered.pdf')
            self.assertEqual(app.session_state['prepared'][0]['pages'][1],'Students may apply to this call.')

    def test_finetune_job_uses_train_and_validation_not_test(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            for name,count in [('train',10),('validation',1),('test',1)]:
                (root/f'{name}.jsonl').write_text(''.join(json.dumps({'messages':[
                    {'role':'system','content':'extract'}, {'role':'user','content':f'{name}-{i}'},
                    {'role':'assistant','content':'{}'}]})+'\n' for i in range(count)))
            client=Mock()
            client.files.create.side_effect=[SimpleNamespace(id='train-file'),SimpleNamespace(id='validation-file')]
            start_job(client,root,'supported-test-model')
            self.assertEqual(client.files.create.call_count,2)
            self.assertEqual(client.fine_tuning.jobs.create.call_args.kwargs['training_file'],'train-file')
            self.assertEqual(client.fine_tuning.jobs.create.call_args.kwargs['validation_file'],'validation-file')

    def test_overall_evaluation_counts_failures_in_denominator(self):
        from evaluate import evaluate
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'a.pdf').write_bytes(sample_pdf())
            system=Mock();system.usage={}
            system.run.return_value={'report':{'status':'신청 가능'}}
            cases=[{'document':'a.pdf','profile':{'학적':'재학'},'expected_status':'신청 가능','reviewed':True},
                   {'document':'missing.pdf','profile':{'학적':'재학'},'expected_status':'신청 가능','reviewed':True}]
            result=evaluate(cases,root,system)
            self.assertEqual(result['accuracy'],0.5)
            self.assertEqual(result['failed'],1)
