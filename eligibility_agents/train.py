"""Streamlit보다 먼저 실행하는 실제 로컬 조항 분류 모델 학습."""
import argparse
import hashlib
import json
import random
from pathlib import Path
import joblib
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.pipeline import Pipeline
from settings import ROOT, load_server_config
from agents import AgentSystem
from parser import ParserAgent, PROMPT
from pdf_utils import pdf_pages
from knowledge import dataset_directory
from validation import normalized
from local_model import MODEL_PATH


def split_samples(samples, seed=42):
    groups={}
    for sample in samples:
        groups.setdefault(sample['document_hash'],[]).append(sample)
    keys=sorted(groups)
    if len(keys)<3:
        raise ValueError('문서별 학습/검증/테스트 분리를 위해 서로 다른 PDF가 최소 3개 필요합니다.')
    random.Random(seed).shuffle(keys)
    count=max(1,len(keys)//10)
    split={'test':keys[:count],'validation':keys[count:count*2],'train':keys[count*2:]}
    return {name:[sample for key in hashes for sample in groups[key]] for name,hashes in split.items()}


def fit_model(splits):
    # Prevent the exact same source sentence leaking across splits even if PDFs differ.
    owners={}
    for name in ('train','validation','test'):
        clean=[]
        for sample in splits[name]:
            text=normalized(sample['text'])
            if text not in owners or owners[text]==name:
                owners[text]=name
                clean.append(sample)
        splits[name]=clean
    training=splits['train']
    if len(training)<10 or len({row['category'] for row in training})<2:
        raise ValueError('학습용으로 인용문 10개 이상과 조항 유형 2종 이상이 필요합니다. PDF를 더 추가해 주세요.')
    if not splits['validation'] or not splits['test']:
        raise ValueError('중복 인용문을 제거한 뒤 검증/테스트 데이터가 비었습니다. 다른 공고를 추가해 주세요.')
    pipeline=Pipeline([
        ('tfidf',TfidfVectorizer(analyzer='char',ngram_range=(2,5),max_features=60000,sublinear_tf=True)),
        ('classifier',LogisticRegression(max_iter=1000,class_weight='balanced',random_state=42))])
    pipeline.fit([r['text'] for r in training],[r['category'] for r in training])
    metrics={}
    for name in ('validation','test'):
        rows=splits[name]
        gold=[r['category'] for r in rows]
        predicted=pipeline.predict([r['text'] for r in rows])
        metrics[name]={'samples':len(rows),'accuracy':accuracy_score(gold,predicted),
                       'macro_f1':f1_score(gold,predicted,average='macro',zero_division=0),
                       'report':classification_report(gold,predicted,output_dict=True,zero_division=0)}
    return pipeline,metrics


def run_training(dataset, system, model_path=MODEL_PATH, work_dir=ROOT/'training'/'local', force=False):
    files=sorted(p for p in dataset.rglob('*') if p.is_file() and p.suffix.lower()=='.pdf')
    if not files:
        raise ValueError('PDF가 없습니다. --dataset으로 PDF 폴더를 지정해 주세요.')
    work_dir.mkdir(parents=True,exist_ok=True)
    cache_path=work_dir/'teacher_cache.json'
    cache=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() and not force else {}
    prompt_hash=hashlib.sha256(PROMPT.encode()).hexdigest()
    samples,failed=[],[]
    for number,path in enumerate(files,1):
        name=path.relative_to(dataset).as_posix()
        system.progress(f'[{number}/{len(files)}] 학습 자료 준비: {name}')
        try:
            if path.stat().st_size>30*1024**2:
                raise ValueError('PDF는 30MB 이하여야 합니다.')
            data=path.read_bytes()
            digest=hashlib.sha256(data).hexdigest()
            key=f'{digest}:{system.model}:{prompt_hash}'
            if key not in cache:
                pages,warnings=pdf_pages(data,system.ocr_page)
                clauses,uncertainties=ParserAgent(system.ask,use_local_model=False).run(pages)
                rows=[]
                seen=set()
                for clause in clauses.values():
                    for evidence in clause['evidence']:
                        identity=(clause['category'],normalized(evidence['quote']))
                        if identity in seen: continue
                        seen.add(identity)
                        rows.append({'document':name,'document_hash':digest,
                                     'page':evidence['page'],'text':evidence['quote'],
                                     'category':clause['category'],'label_source':'GPT silver label (human-unreviewed)'})
                cache[key]={'samples':rows,'warnings':warnings+uncertainties}
                temporary=cache_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(cache,ensure_ascii=False),encoding='utf-8')
                temporary.replace(cache_path)
            samples.extend({**r,'document':name} for r in cache[key]['samples'])
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) else type(error).__name__
            failed.append({'document':name,'error':reason})
    if failed:
        (work_dir/'failed_documents.json').write_text(json.dumps(failed,ensure_ascii=False,indent=2),encoding='utf-8')
        raise ValueError('일부 학습 PDF 처리에 실패했습니다. training/local/failed_documents.json을 확인하고 다시 실행해 주세요. 성공한 자료는 캐시했습니다.')
    # Same bytes under different filenames stay in one group and are not weighted twice.
    samples=list({(r['document_hash'],r['category'],normalized(r['text'])):r for r in samples}.values())
    splits=split_samples(samples)
    pipeline,metrics=fit_model(splits)
    summary={'model_type':'TF-IDF character n-grams + LogisticRegression',
             'label_source':'GPT-generated silver labels; not human ground truth',
             'scope':'공고 조항 유형 분류. GPT 재학습 또는 최종 적격 판정 모델 학습이 아님.',
             'teacher_model':system.model,'metrics':metrics,
             'split':{name:{'samples':len(rows),'documents':sorted({r['document_hash'] for r in rows})}
                      for name,rows in splits.items()},'preparation_api_usage':system.usage}
    model_path.parent.mkdir(parents=True,exist_ok=True)
    tmp=model_path.with_suffix('.tmp')
    joblib.dump({'pipeline':pipeline,'metadata':summary},tmp)
    tmp.replace(model_path)
    (model_path.parent/'training_metrics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,rows in splits.items():
        (work_dir/f'{name}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser(description='PDF 폴더로 로컬 조항 분류 모델 학습 (Streamlit 실행 전)')
    parser.add_argument('--dataset')
    parser.add_argument('--force',action='store_true',help='GPT 임시 라벨도 다시 생성')
    args=parser.parse_args()
    try:
        config=load_server_config()
        if not config.api_key: raise ValueError('.env에 API 키를 설정해야 합니다.')
        system=AgentSystem(config.model,OpenAI(api_key=config.api_key,timeout=120,max_retries=2),progress=print)
        result=run_training(dataset_directory(args.dataset),system,force=args.force)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        print('로컬 조항 분류 모델 학습 완료. 이제 python -m streamlit run app.py 를 실행하세요.')
        return 0
    except Exception as error:
        print(str(error) if isinstance(error,ValueError) else '학습 실패: '+type(error).__name__)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
