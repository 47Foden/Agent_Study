"""사람이 판정한 테스트 사례로 전체 에이전트의 신청 가능 여부를 평가한다."""
import argparse
import hashlib
import json
from pathlib import Path
from openai import OpenAI
from settings import ROOT, load_server_config
from knowledge import dataset_directory, load_index, search
from agents import AgentSystem
from pdf_utils import pdf_pages


def evaluate(cases, dataset, system, index=None, excluded_hashes=None):
    valid={'신청 가능','신청 불가','추가 확인 필요'}
    if not cases or any(row.get('reviewed') is not True or row.get('expected_status') not in valid for row in cases):
        raise ValueError('사람이 expected_status를 판정하고 reviewed=true로 검수한 테스트 사례가 필요합니다.')
    correct,details=0,[]
    for case in cases:
        try:
            path=(dataset/case['document']).resolve()
            if not path.is_relative_to(dataset.resolve()):
                raise ValueError('테스트 PDF는 지정한 데이터셋 폴더 안에 있어야 합니다.')
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest() in (excluded_hashes or set()):
                raise ValueError('이 문서는 Parser 학습/검증 분할에 포함되어 테스트 평가에서 제외합니다.')
            pages,warnings=pdf_pages(data,system.ocr_page)
            context=[]
            if index:
                context,_=search(index,json.dumps(case['profile'],ensure_ascii=False)+' 신청 자격 제외 제재',
                                 system.client,hashlib.sha256(data).hexdigest())
            result=system.run(case['document'],pages,case['profile'],warnings,retrieved_context=context)
            predicted=result['report']['status']
            correct+=int(predicted==case['expected_status'])
            details.append({'document':case['document'],'expected':case['expected_status'],
                            'predicted':predicted,'correct':predicted==case['expected_status']})
        except Exception as error:
            details.append({'document':case.get('document'),
                            'error':str(error) if isinstance(error,ValueError) else type(error).__name__})
    return {'cases':len(cases),'correct':correct,'failed':sum('error' in d for d in details),
            'accuracy':correct/len(cases),'details':details,'usage':system.usage}


def main():
    parser=argparse.ArgumentParser(description='전체 적격 판정의 테스트 정확도 측정 (유료 API 호출)')
    parser.add_argument('--cases',required=True,type=Path)
    parser.add_argument('--dataset')
    parser.add_argument('--output',type=Path,default=ROOT/'evaluation'/'eligibility_metrics.json')
    args=parser.parse_args()
    try:
        config=load_server_config()
        if not config.api_key: raise ValueError('.env에 API 키를 설정해야 합니다.')
        cases=[json.loads(line) for line in args.cases.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        system=AgentSystem(config.model,OpenAI(api_key=config.api_key,timeout=120,max_retries=2))
        system.parser_model=config.parser_model
        manifest_path=ROOT/'training'/'split_manifest.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
        excluded={digest for split in ('train','validation') for digest in manifest.get(split,{}).get('document_hashes',[])}
        result=evaluate(cases,dataset_directory(args.dataset),system,load_index(),excluded)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 1 if result['failed'] else 0
    except Exception as error:
        print(str(error) if isinstance(error,ValueError) else '평가 실패: '+type(error).__name__)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
