# 브랜치 구성

- `main`: 공통 UI, 실행 제어, 설정, 학습·평가 도구, 테스트 및 데이터
- `feature/Parser`: `eligibility_agents/parser.py`
- `feature/ProCritique`: `eligibility_agents/procritique.py` (Pro / Critic)
- `feature/Writer`: `eligibility_agents/writer.py`

각 에이전트 브랜치에는 main의 공통 파일도 포함합니다. 전체 앱 실행에는 세 에이전트 구현이 모두 필요합니다. 통합 브랜치에서 세 feature 브랜치를 병합한 뒤 `eligibility_agents/README.md`를 따르세요.

실제 `.env`, `.env.example`, Streamlit `secrets.toml`, 개인 프로필, 가상환경, 캐시 및 학습 산출물은 커밋하지 않습니다. `.env.template`을 로컬 `.env`로 복사해 설정하세요.
