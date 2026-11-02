"""관리자용: python build_dataset.py --dataset ./데이터셋"""
import argparse
from pathlib import Path
from openai import OpenAI
from settings import load_server_config
from agents import AgentSystem
from knowledge import build, dataset_directory, INDEX_PATH, EMBEDDING_MODEL
import json


def main():
    parser = argparse.ArgumentParser(description='PDF 폴더를 RAG 지식 색인으로 변환 (GPT 재학습 아님)')
    parser.add_argument('--dataset', help='프로젝트 안 폴더명 또는 절대 경로')
    parser.add_argument('--output', type=Path, default=INDEX_PATH)
    parser.add_argument('--embedding-model', default=EMBEDDING_MODEL)
    parser.add_argument('--force', action='store_true', help='이미 처리한 PDF도 다시 색인')
    args = parser.parse_args()
    try:
        config = load_server_config()
        if not config.api_key:
            raise ValueError('.env의 OPENAI_API_KEY를 설정해야 합니다.')
        system = AgentSystem(config.model, OpenAI(api_key=config.api_key,timeout=120,max_retries=2),progress=print)
        index = build(dataset_directory(args.dataset), system, args.output, args.embedding_model,args.force)
        print(json.dumps(index['build_summary'],ensure_ascii=False,indent=2))
        print('지식 색인 저장 완료. GPT 모델의 가중치는 변경되지 않았습니다.')
        return 1 if index['build_summary']['failed'] else 0
    except Exception as error:
        print(str(error) if isinstance(error,ValueError) else f'구축 실패: {type(error).__name__}')
        return 1

if __name__=='__main__':
    raise SystemExit(main())
