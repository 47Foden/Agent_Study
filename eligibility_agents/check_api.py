"""키를 출력하지 않고 실제 모델 호출을 확인한다: python check_api.py"""
import argparse
from openai import OpenAI
from settings import load_server_config


def check(config, client=None, embeddings=False):
    if not config.api_key:
        raise ValueError('키가 없습니다. app.py와 같은 폴더의 .env에 OPENAI_API_KEY를 설정해 주세요.')
    client = client or OpenAI(api_key=config.api_key, timeout=30, max_retries=0)
    response = client.responses.create(model=config.model, input='Reply with OK only.', store=False)
    if not response.output_text.strip():
        raise ValueError('모델 응답이 비어 있습니다.')
    if embeddings:
        client.embeddings.create(model='text-embedding-3-small', input=['API connection test'])
    return 'API 연결 성공: 설정된 모델이 응답했습니다.'


def main():
    parser = argparse.ArgumentParser(description='실제 API 연결 확인 (소량의 API 비용 발생)')
    parser.add_argument('--embeddings',action='store_true',help='데이터셋 임베딩 API도 확인')
    args=parser.parse_args()
    try:
        print(check(load_server_config(), embeddings=args.embeddings))
        return 0
    except Exception as error:
        messages={'AuthenticationError':'API 키가 유효하지 않습니다.',
                  'PermissionDeniedError':'모델 또는 프로젝트 접근 권한을 확인해 주세요.',
                  'RateLimitError':'API 결제·크레딧·사용 한도 또는 속도 제한을 확인해 주세요.',
                  'NotFoundError':'설정한 모델 이름과 사용 권한을 확인해 주세요.',
                  'APIConnectionError':'네트워크 연결을 확인해 주세요.'}
        print(str(error) if isinstance(error,ValueError) else messages.get(type(error).__name__,'연결 실패: '+type(error).__name__))
        return 1

if __name__=='__main__':
    raise SystemExit(main())
