"""실제 Parser 지도 파인튜닝: PDF만으로 학습하지 않고 사람이 검수한 정답을 사용한다."""
import argparse
import hashlib
import json
import random
from pathlib import Path
from openai import OpenAI
from settings import ROOT, load_server_config
from knowledge import load_index
from schemas import Extraction
from validation import validate_evidence
from parser import PROMPT
from llm_client import BASE

TRAINING = ROOT / 'training'


def init_labels(index, output):
    if output.exists():
        raise ValueError('기존 정답 파일을 덮어쓰지 않습니다. 다른 --output 경로를 사용해 주세요.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8') as handle:
        for doc in index['documents']:
            for page,text in doc['pages'].items():
                if text.strip():
                    row={'document':doc['name'],'document_hash':doc['sha256'],'page':int(page),
                         'text':text,'reviewed':False,'expected_extraction':None}
                    handle.write(json.dumps(row,ensure_ascii=False)+'\n')


def prepare(labels, output, seed=42):
    rows = [json.loads(line) for line in labels.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    if not rows or any(row.get('reviewed') is not True or row.get('expected_extraction') is None for row in rows):
        raise ValueError('모든 항목의 expected_extraction을 사람이 작성하고 reviewed를 true로 바꿔야 합니다.')
    groups={}
    for row in rows:
        if not row.get('document_hash') or not row.get('text') or len(row['text'])>12000:
            raise ValueError('문서 해시/텍스트가 필요하며 한 학습 텍스트는 12000자 이하여야 합니다.')
        expected=Extraction.model_validate(row['expected_extraction'])
        validate_evidence(expected,{int(row['page']):row['text']})
        messages=[{'role':'system','content':BASE+'\n'+PROMPT},
                  {'role':'user','content':json.dumps({'page':int(row['page']),'text':row['text']},ensure_ascii=False)},
                  {'role':'assistant','content':expected.model_dump_json()}]
        groups.setdefault(row['document_hash'],[]).append({'messages':messages})
    keys=sorted(groups)
    if len(keys)<3:
        raise ValueError('문서 단위 분리를 위해 내용이 서로 다른 PDF가 최소 3개 필요합니다.')
    random.Random(seed).shuffle(keys)
    test_size=max(1,len(keys)//10)
    valid_size=max(1,len(keys)//10)
    split={'test':keys[:test_size], 'validation':keys[test_size:test_size+valid_size],
           'train':keys[test_size+valid_size:]}
    seen = {}
    for name, hashes in split.items():
        for digest in hashes:
            for row in groups[digest]:
                text = row['messages'][1]['content']
                if text in seen and seen[text] != name:
                    raise ValueError('동일한 페이지 입력이 서로 다른 분할에 있습니다. 중복 공고를 정리해 주세요.')
                seen[text] = name
    output.mkdir(parents=True,exist_ok=True)
    summary={}
    for name, hashes in split.items():
        samples=[row for digest in hashes for row in groups[digest]]
        (output/f'{name}.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in samples),encoding='utf-8')
        summary[name]={'documents':len(hashes),'examples':len(samples),'document_hashes':hashes}
    (output/'split_manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def start_job(client, folder, model):
    train_path, validation_path = folder/'train.jsonl', folder/'validation.jsonl'
    def rows(path):
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    train, validation = rows(train_path), rows(validation_path)
    if len(train)<10:
        raise ValueError('학습 예시를 최소 10개 준비해야 합니다. 페이지별 정답을 더 작성해 주세요.')
    if not validation:
        raise ValueError('검증 예시가 없습니다.')
    train_inputs={r['messages'][1]['content'] for r in train}
    if any(r['messages'][1]['content'] in train_inputs for r in validation):
        raise ValueError('학습·검증 예시에 동일 입력이 포함되어 있습니다.')
    with train_path.open('rb') as handle:
        training_file=client.files.create(file=handle,purpose='fine-tune')
    with validation_path.open('rb') as handle:
        validation_file=client.files.create(file=handle,purpose='fine-tune')
    return client.fine_tuning.jobs.create(training_file=training_file.id,
        validation_file=validation_file.id,model=model,method={'type':'supervised'})


def main():
    parser=argparse.ArgumentParser(description='Parser 파인튜닝: 정답 작성 → 문서별 분리 → 학습')
    commands=parser.add_subparsers(dest='command',required=True)
    initialize=commands.add_parser('init-labels')
    initialize.add_argument('--output',type=Path,default=TRAINING/'labels.jsonl')
    prep=commands.add_parser('prepare')
    prep.add_argument('--labels',type=Path,default=TRAINING/'labels.jsonl')
    prep.add_argument('--output',type=Path,default=TRAINING)
    start=commands.add_parser('start')
    start.add_argument('--folder',type=Path,default=TRAINING)
    start.add_argument('--base-model',required=True,help='계정에서 파인튜닝을 지원하는 OpenAI 모델 ID')
    start.add_argument('--eligible-existing-customer',action='store_true',help='기존 파인튜닝 이용 자격을 확인한 계정만 사용')
    status=commands.add_parser('status')
    status.add_argument('--job-id',required=True)
    args=parser.parse_args()
    try:
        if args.command=='init-labels':
            index=load_index()
            if not index: raise ValueError('먼저 build_dataset.py를 실행해야 합니다.')
            init_labels(index,args.output)
            print('정답 입력 양식을 만들었습니다. 아직 학습하지 않았습니다.')
        elif args.command=='prepare':
            print(json.dumps(prepare(args.labels,args.output),ensure_ascii=False,indent=2))
        else:
            config=load_server_config()
            if not config.api_key: raise ValueError('.env에 API 키를 설정해야 합니다.')
            client=OpenAI(api_key=config.api_key,timeout=120,max_retries=2)
            if args.command=='start':
                if not args.eligible_existing_customer:
                    raise ValueError('현재 OpenAI 파인튜닝은 신규 사용자에게 제공되지 않습니다. 기본 학습은 python train.py를 사용하세요. 기존 이용 자격을 확인한 경우에만 --eligible-existing-customer를 지정하세요.')
                job=start_job(client,args.folder,args.base_model)
                print(f'실제 유료 파인튜닝 작업을 제출했습니다. job_id: {job.id}')
            else:
                job=client.fine_tuning.jobs.retrieve(args.job_id)
                print(json.dumps({'status':job.status,'fine_tuned_model':job.fine_tuned_model},ensure_ascii=False))
        return 0
    except Exception as error:
        print(str(error) if isinstance(error,ValueError) else '처리 실패: '+type(error).__name__)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
