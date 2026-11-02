# 공고핏

**현재 권장 실행 순서는 [TRAIN_FIRST.md](TRAIN_FIRST.md)의 `train.py` → `app.py`다.**

학습 대상은 로컬 조항 분류기(TF-IDF + LogisticRegression)이며 GPT의 가중치를 바꾸지 않는다.
PDF에서 GPT가 생성한 임시 라벨로 학습하며 검증 지표는 사람 정답 기준이 아닌 silver-label 기준이다.

```powershell
python -m pip install -r requirements.txt
python train.py --dataset ".\데이터셋"
python -m streamlit run app.py
```


**PDF 폴더 등록·API 키 확인·실제 학습·테스트는 [DATASET_TRAINING.md](DATASET_TRAINING.md)를 확인한다.**

공고 PDF와 신청자 프로필을 대조해 지원 적격성과 결격 위험을 검토하는 Streamlit 서비스다.
PDF/ZIP 업로드 → 자동 문서 준비 → 프로필 작성 → 에이전트 토론 → 보고서 다운로드 순서로 사용한다.

## 기존 버전에서 업데이트

서버를 Ctrl+C로 종료하고 이 ZIP의 `eligibility_agents` 폴더 내용물을 기존 폴더에 덮어쓴다.
**기존 `.env.example` 또는 `.env` 파일은 삭제하지 않는다.**
이번 ZIP에는 `.env.example`을 포함하지 않아 기존 키를 덮어쓰지 않는다.
기존 `.env.example`에 실제 API 키가 있다면 시작 시 서버가 `.env`로 옮긴 뒤 예시 파일의 키 값을 비운다.
이 작업은 사용자의 PC에서 실행할 때 이루어진다. 기존 `.env`에 다른 키가 있으면 덮어쓰지 않고 오류로 중단한다.
실제 키는 화면 입력란, 다운로드 파일, 세션 상태에 넣지 않는다.
API 키 입력란은 제거했으며 모델·토론 횟수도 서버 설정에서 관리한다.

## VS Code 실행

`app.py`가 있는 폴더를 열고 터미널에서 실행한다. Python 3.10 이상이 필요하다.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

브라우저에서 http://localhost:8501 에 접속한다. 개별 에이전트 파일을 순서대로 실행할 필요는 없다.
`app.py`가 `agents.py`를 통해 필요한 에이전트를 자동 호출한다.
완전히 새로 설치한다면 `.env.template`을 `.env`로 복사한 뒤 실제 키를 입력한다.
기존 키 파일이 있으면 복사하지 않는다.

```dotenv
OPENAI_API_KEY=본인의_API키
OPENAI_MODEL=gpt-4o-mini
APP_PASSWORD=
DEBATE_ROUNDS=2
```

APP_PASSWORD를 설정하면 접속 비밀번호를 요구한다. 비워두면 비밀번호 없이 사용할 수 있다.
실제 키가 없으면 분석이 비활성화되고 서비스 준비 안내만 표시된다.
서버 키와 프로필은 OpenAI API 요청에만 사용한다. 프로필은 결과 JSON에도 포함된다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `app.py` | 공고핏 화면, 업로드, 프로필 폼, 진행 상태, 다운로드 |
| `agents.py` | Parser → Pro/Critic 반복 → Writer의 실행 순서와 CLI |
| `parser.py` | ParserAgent: 핵심 조항 추출, 페이지·인용 검증 |
| `procritique.py` | ProAgent와 CriticAgent: 지원 근거 검토와 위험 반박 |
| `writer.py` | WriterAgent: 최종 판정, 결격 최대 3개, 보완사항 |
| `llm_client.py` | OpenAI Responses API 호출, 공유 지시문, 토큰 집계 |
| `schemas.py` | 조항·주장·보고서의 Pydantic 형식 |
| `validation.py` | 원문 인용, 조항 ID, 프로필 참조 검증 |
| `pdf_utils.py` | ZIP/PDF 읽기, 자동 텍스트 추출, 스캔 감지·페이지 렌더링 |
| `ocr.py` | 스캔 페이지의 GPT Vision 문자 인식 |
| `settings.py` | 서버 설정, 기존 키 파일 이전 |
| `tests/` | 모의 API/Streamlit 화면/키 이전 테스트 |
| `DEPLOY.md` | GitHub 업로드와 Streamlit Cloud 배포 |

역할별 프롬프트와 처리 로직은 해당 에이전트 파일에서 수정한다.
Pro와 Critic은 같은 파일 안에 별도 클래스로 구성했으며 각각 독립된 GPT 호출을 수행한다.
기본 토론 흐름은 Parser → Pro → Critic → Pro → Critic → Writer다.

## 근거와 판정

Parser가 모든 추출 텍스트를 순차 검토하고 인용문이 해당 페이지에 존재하는지 검증한다.
Pro/Critic/Writer가 실제 조항 ID와 프로필 키를 참조하는지도 검증한다.
미해결 쟁점이나 텍스트 추출 경고가 남으면 확정적인 신청 가능 판정을 보류한다.
치명적 결격 사유는 확인된 불충족만 최대 3개 표시한다. 개수를 채우려고 만들지 않는다.
인용의 존재 검증이 해석의 정확성까지 보장하지는 않으므로 보고서의 페이지와 원문을 대조해야 한다.
로컬 JSON 벡터 색인으로 등록된 공고의 관련 조항을 검색한다. 모델 자율 function calling과 외부 웹 검색은 포함하지 않았다.

## 입력 범위와 출력

- PDF 한 개가 공고 한 건이다. 동일 공고의 본문·별첨은 한 PDF로 병합해 올린다.
- PDF 업로드 즉시 텍스트를 추출하고, 스캔·이미지 본문이 있는 페이지는 자동으로 인식 대기 상태로 준비한다.
- 전송 동의 후 분석을 시작하면 필요한 페이지를 GPT Vision으로 문자 인식하고 Parser가 조항 추출을 이어간다. 별도 OCR 프로그램 설치는 필요 없다.
- OCR에는 추가 OpenAI API 사용료가 발생한다. 작은 글자/표/흐릿한 한글은 오인식할 수 있어 원본 대조 경고를 보고서에 남긴다.
- 지원 가능 확정은 OCR 원문 대조가 필요한 경우 보류한다.
- 웹 업로드 최대 50MB, 개별 PDF 최대 30MB/500페이지, ZIP 내 PDF 최대 100개/비압축 합계 200MB.
- 웹에서 한 번에 최대 5개 공고를 선택한다.
- 검토 입력이 18만 자를 넘으면 해당 PDF를 오류 처리한다. 모델별 토큰 한도는 추가로 적용된다.
- 보고서 Markdown, 전체 분석 JSON, 전체 결과 ZIP을 다운로드할 수 있다.
- 웹 결과는 세션 메모리에 보관한다. 영구 저장/계정별 이력 기능은 없다.
- CLI는 `outputs`에 추출 텍스트, 보고서, 토론과 사용량을 저장한다.
- API 사용료가 발생하며 재분석 버튼을 누르면 다시 호출한다. 운영자 키 사용 시 운영자 계정에 청구된다.

## CLI (선택 사항)

```powershell
.\.venv\Scripts\python.exe agents.py --input "데이터셋.zip" --extract-only
.\.venv\Scripts\python.exe agents.py --input "데이터셋.zip" --profile profile.json --rounds 2
```

`profile.example.json`을 실제 정보로 수정해 `profile.json`으로 저장한 뒤 사용한다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

32개 테스트가 통과했다. 모의 API 전체 토론, 보고서 화면, 재실행 시 중복 호출 방지,
키 파일 이전, 저장 실패 시 원본 보존, 서버 키 화면 비노출 등을 확인했다.
생성한 텍스트형·스캔형·혼합형 PDF로 페이지 추출과 OCR 연결을 검증했다. 이미지 전송은 모의 API로 검사했다.
실제 사용자 키·데이터셋으로 OCR/API 실행 및 Cloud 배포를 검증한 상태는 아니다.

## 이번 업데이트 적용

서버를 종료하고 파일을 덮어쓴 뒤 추가된 PDF 렌더링 패키지를 한 번 설치한다.
기존 `.env` / `.env.example`은 보존한다.

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

수동 텍스트 추출 버튼과 별도 예산 입력란을 제거했다.
분석에 자부담/재정 조건이 필요한 공고라면 추가 사실에만 선택적으로 적을 수 있다.
서버를 재시작한 뒤 PDF를 다시 업로드하면 새 자동 준비 흐름이 적용된다.
스캔 PDF를 `--extract-only`로 실행하면 외부 전송 없이 OCR 필요 페이지를 표시한다.
실제 CLI 분석에서는 OCR과 Parser/토론/Writer를 순차 실행한다.

## 새 데이터셋·학습 도구

| 파일 | 용도 |
|---|---|
| `build_dataset.py` | PDF 폴더 → OCR/텍스트 → 임베딩 → RAG 색인 |
| `knowledge.py` | 색인 저장·캐시·공고별 벡터 검색 |
| `check_api.py` | 키를 출력하지 않고 실제 API 연결 확인 |
| `train_parser.py` | 정답 양식 생성, 문서 단위 분리, 실제 Parser 파인튜닝 |
| `evaluate_parser.py` | 보류 테스트셋의 조항 추출 precision/recall/F1 |
| `evaluate.py` | 정답 프로필 사례의 최종 적격 판정 정확도 |

PDF 폴더만 넣은 단계는 실제 지도학습 완료가 아니다. 정답을 검수한 뒤 파인튜닝해야 한다.
학습·검증·테스트 분리나 연결 단위 테스트 통과가 실제 모델 성능을 보장하지 않는다.

`train.py`는 실제 로컬 분류기를 학습한다. `local_model.py`가 저장 모델을 로드해 Parser에 조항 유형 예측을 제공한다. 기본 설정에서는 학습 모델이 없으면 웹 분석을 비활성화한다.
