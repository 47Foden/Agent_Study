"""보류한 정답 테스트 예시로 Parser의 추출 precision/recall/F1 측정."""
import argparse
import json
from pathlib import Path
from openai import OpenAI
from settings import load_server_config, ROOT
from llm_client import LLMClient
from parser import PROMPT
from schemas import Extraction
from validation import normalized, validate_evidence


def facts(extraction):
    return {(clause.category,e.page,normalized(e.quote)) for clause in extraction.clauses for e in clause.evidence}


def evaluate(cases, system):
    correct=predicted=expected_count=errors=0
    details=[]
    for number,row in enumerate(cases,1):
        expected=Extraction.model_validate_json(row['messages'][2]['content'])
        payload=json.loads(row['messages'][1]['content'])
        gold=facts(expected)
        expected_count+=len(gold)
        try:
            prediction=system.ask(PROMPT,payload,Extraction)
            validate_evidence(prediction,{int(payload['page']):payload['text']})
            got=facts(prediction)
            correct+=len(got & gold)
            predicted+=len(got)
            details.append({'case':number,'matched':len(got & gold),'predicted':len(got),'expected':len(gold)})
        except Exception as error:
            errors+=1
            details.append({'case':number,'error':str(error) if isinstance(error,ValueError) else type(error).__name__})
    precision=correct/predicted if predicted else 0.0
    recall=correct/expected_count if expected_count else 0.0
    return {'cases':len(cases),'failed':errors,'matched':correct,'expected':expected_count,'predicted':predicted,
            'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0.0,
            'metric':'조항 유형+물리적 페이지+공백 제거 인용문 exact match (의미 유사도 점수 아님)',
            'model':system.parser_model or system.model,'details':details,'usage':system.usage}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--test',type=Path,default=ROOT/'training'/'test.jsonl')
    parser.add_argument('--model',help='미지정 시 OPENAI_PARSER_MODEL 또는 OPENAI_MODEL')
    parser.add_argument('--output',type=Path,default=ROOT/'evaluation'/'parser_metrics.json')
    args=parser.parse_args()
    try:
        config=load_server_config()
        if not config.api_key: raise ValueError('.env에 API 키를 설정해야 합니다.')
        cases=[json.loads(line) for line in args.test.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        if not cases: raise ValueError('테스트 예시가 없습니다.')
        system=LLMClient(args.model or config.parser_model or config.model,
                         OpenAI(api_key=config.api_key,timeout=120,max_retries=2))
        result=evaluate(cases,system)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False,indent=2))
        return 1 if result['failed'] else 0
    except Exception as error:
        print(str(error) if isinstance(error,ValueError) else '평가 실패: '+type(error).__name__)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
