# 학습 모델 배포 선행 조건

현재 버전은 `python train.py --dataset ".\데이터셋"`으로 학습한 모델을 기본으로 요구한다.
먼저 TRAIN_FIRST.md를 읽는다. 배포 서버에도 생성된 models/clause_classifier.joblib을 제공해야 한다.

# 공고핏 실행 및 Streamlit 배포

## 1. 기존 키를 유지하며 업데이트

1. 실행 중인 서버 터미널에서 Ctrl+C를 누른다.
2. 이 ZIP을 임시 폴더에 풀고 `eligibility_agents` 안의 파일을 기존 프로젝트 폴더에 덮어쓴다.
3. 기존 `.env.example` 또는 `.env`를 삭제하지 않는다. 이번 ZIP에는 `.env.example`이 없다.
4. 기존 `.env.example`에 키를 넣어뒀다면 첫 실행 때 `.env`로 이전하고 예시 파일의 실제 키는 비운다.
   기존 `.env`에 서로 다른 키가 있으면 자동 변경하지 않으므로 운영자가 원하는 키를 정리해야 한다.

현재 사용자 PC의 키를 이 대화에서 읽거나 수정한 상태는 아니다. 이전은 다음 실행 시 로컬에서 이루어진다.

## 2. VS Code에서 실행

`app.py`가 있는 폴더를 열고 터미널에서 실행한다.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

http://localhost:8501 접속 → PDF/ZIP 업로드 → 자동 문서 준비 → 분석할 공고 선택 → 신청자 정보 입력 → 분석.
각 에이전트 파일은 직접 실행하지 않는다. Ctrl+C로 서버를 종료한다.

새 설치이며 기존 키 파일이 전혀 없을 때만 `.env.template`을 `.env`로 복사하고 값을 입력한다.
기존 `.env`를 덮어쓰지 않도록 한다.

```dotenv
OPENAI_API_KEY=본인의_API키
OPENAI_MODEL=gpt-4o-mini
APP_PASSWORD=
DEBATE_ROUNDS=2
```

`.env`나 서버 환경변수 설정 변경 후에는 서버를 재시작한다.
APP_PASSWORD를 설정하면 비밀번호 입력을 요구한다. 빈 값이면 공개 접속 모드다.
모델과 토론 횟수는 화면에 노출하지 않고 서버 설정으로만 관리한다.

## 3. GitHub에 코드 반영

복사할 때는 파일을 저장소 루트에 배치하는 것을 권장한다.
이미 clone한 저장소라면 해당 저장소에서 `git status`로 변경 사항을 확인한다.

이전 `.env.example`에 실제 키를 넣은 상태로 추적한 적이 있다면 아래 명령으로 추적에서 제외한다.
파일 자체는 지우지 않는다.

```powershell
git rm --cached --ignore-unmatch .env.example .env .streamlit/secrets.toml
```

그다음 소스 파일만 선택해 올린다. 키 파일과 실제 데이터셋은 올리지 않는다.

```powershell
git add app.py agents.py parser.py procritique.py writer.py llm_client.py schemas.py validation.py pdf_utils.py ocr.py settings.py requirements.txt README.md DEPLOY.md .gitignore .env.template .streamlit/config.toml .streamlit/secrets.example.toml tests start.ps1 profile.example.json
git commit -m "Rename to GonggoFit and split agents with server-side credentials"
git push
```

위 경로는 저장소 루트에 코드가 있는 경우다. `eligibility_agents` 하위 폴더에 뒀다면 그 위치에 맞게 실행한다.
팀 브랜치 정책에 따라 main에 직접 push하거나 작업 브랜치의 PR로 병합한다.
`.gitignore`는 과거 Git 이력에서 키를 지우지 않는다. 실제 키를 원격에 올렸다면 해당 키를 폐기하고 새 키로 교체한다.

## 4. Streamlit Community Cloud

1. https://share.streamlit.io 에 GitHub 계정으로 로그인한다.
2. Create app에서 저장소·브랜치를 고르고 진입점으로 `app.py`를 지정한다.
   하위 폴더로 올렸다면 `eligibility_agents/app.py`다.
3. Advanced settings에서 Python 3.12를 선택하고 Secrets에 다음 TOML을 실제 값으로 입력한다.
4. 배포하고 생성된 `https://...streamlit.app` 주소로 접속한다.

```toml
OPENAI_API_KEY = "본인의_API키"
OPENAI_MODEL = "gpt-4o-mini"
APP_PASSWORD = "서비스접속용_긴_비밀번호"
DEBATE_ROUNDS = 2
```

비밀번호 없이 공개하려면 APP_PASSWORD를 빈 값으로 지정한다.
방문자의 사용료도 운영자 키의 계정에 청구된다.
로컬 `.env`는 업로드하지 않으므로 Cloud Secrets를 별도로 설정한다.
서버 설정 우선순위는 Cloud Secrets → 환경변수 → 프로젝트의 `.env`다.
키가 없을 때 방문자에게 키를 입력받는 대체 모드는 없다.

## 5. 배포 확인

텍스트 PDF와 스캔 PDF로 업로드 → 자동 준비 → 분석 → 인용·페이지 확인 → 다운로드를 점검한다.
스캔 페이지는 전송 동의 후 GPT Vision으로 자동 인식한다. 추가 OCR 프로그램 설치 없이 requirements.txt 설치만 필요하다.
모델은 이미지 입력과 Structured Outputs를 지원해야 한다. 기본 gpt-4o-mini를 사용할 수 있다.
실제 키, 계정 권한, 결제/한도, 모델 사용 가능 여부에 따라 API 오류가 날 수 있다.
모의 API/화면/설정 테스트 32개는 통과했으며 실제 API 및 Cloud 배포는 별도 검증 대상이다.
이 코드는 공유 비밀번호를 선택적으로 지원하는 MVP다. 계정별 회원관리·사용 한도·결제 기능은 포함하지 않았다.

공식 배포 문서:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

공식 Secrets 문서:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

데이터셋 등록과 파인튜닝·평가는 DATASET_TRAINING.md를 따른다. 로컬 PC의 PDF 폴더는 배포 서버에 자동 복사되지 않는다.
