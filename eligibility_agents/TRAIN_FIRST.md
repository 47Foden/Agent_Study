# 먼저 학습하고, 새 PDF를 서비스에서 분석하기

## 이번 버전의 학습 대상

**실제 학습 대상은 로컬 조항 분류기(TF-IDF + LogisticRegression)다.**
GPT의 가중치는 변경하지 않는다. OpenAI GPT는 학습용 임시 라벨 생성과 새 PDF의 조항 추출·설명에 사용한다.
RAG 색인 구축은 학습과 다르며, 이번 흐름에는 `build_dataset.py`를 먼저 실행할 필요가 없다.

OpenAI 공식 문서는 파인튜닝 신규 사용자 접근이 종료됐다고 안내한다.
따라서 이전 `train_parser.py start`를 기본 학습 경로로 안내한 것은 현재 신규 사용자에게 적합하지 않았다.
이번에는 Windows PC에서 CPU로 학습하고 저장하는 자체 모델을 기본으로 사용한다.
GPU나 CUDA는 필요하지 않다. GPT API 비용은 데이터 준비/OCR/라벨 생성 및 서비스 추론 때 발생한다.

공식 안내: https://developers.openai.com/api/docs/guides/supervised-fine-tuning

## 1. 업데이트

서버를 Ctrl+C로 종료하고 ZIP 내용물을 기존 eligibility_agents 폴더에 덮어쓴다.
`.env`, `.env.example`, 데이터셋 폴더, 이전에 학습한 `models`는 삭제하지 않는다.
새 패키지를 설치한다. 가상환경을 활성화한 상태에서 아래 명령을 사용한다.

```powershell
python -m pip install -r requirements.txt
```

## 2. API 연결 확인

프로젝트의 `.env`에 현재 유효한 API 키와 이미지·구조화 출력 지원 모델을 설정한다.
예:

```dotenv
OPENAI_API_KEY=실제_API키
OPENAI_MODEL=gpt-6-luna
REQUIRE_TRAINED_MODEL=true
```

```powershell
python check_api.py
```

키가 화면에 출력되지는 않는다. API 잔액과 해당 모델 사용 권한이 필요하다.
이전 `.env.example`의 키 자동 이전도 유지한다.

## 3. 먼저 데이터셋 PDF로 학습

PDF 폴더 이름이 `데이터셋`이고 eligibility_agents 안에 있다면:

```powershell
python train.py --dataset ".\데이터셋"
```

다른 이름이면 해당 폴더 이름으로 바꾼다. 하위 폴더 PDF도 읽는다.
`--dataset` 생략 시 dataset/datasets/데이터셋 중 PDF가 있는 폴더를 찾는다.

실행 과정:

1. PDF 텍스트 추출. 스캔 페이지는 GPT Vision으로 문자 인식한다.
2. GPT가 원문에 근거한 조항 유형 임시 라벨을 생성한다.
3. 인용문이 원문에 존재하는지 검증하고 학습 예시를 만든다.
4. 같은 PDF가 섞이지 않도록 문서 단위로 학습/검증/테스트를 약 80/10/10 분리한다.
5. 문장·조항의 문자 n-gram TF-IDF를 만들고 LogisticRegression의 가중치를 실제 학습한다.
6. 검증/테스트 조항 유형 accuracy와 macro F1을 계산하고 모델 파일을 저장한다.

내용이 서로 다른 PDF 최소 3개가 필요하다. 학습 분할에는 인용문 10개 이상과 조항 유형 2종 이상이 필요하다.
문서 전체를 읽어 PDF만 외우는 모델이 아니라 새로운 문장의 조항 유형을 분류하는 모델이다.
학습/검증/테스트 사이의 완전히 같은 문장은 제거하며 중복 제거 후 평가셋이 비면 중단한다.

생성 파일:

| 파일 | 내용 |
|---|---|
| `models/clause_classifier.joblib` | 실제 학습된 로컬 모델 |
| `models/training_metrics.json` | 모델 종류, 데이터 분리, 검증/테스트 지표 |
| `training/local/train.jsonl` | 학습용 인용문·조항 유형 |
| `training/local/validation.jsonl` | 검증용 자료 |
| `training/local/test.jsonl` | 테스트용 자료 |
| `training/local/teacher_cache.json` | GPT 라벨 결과 캐시 |

데이터 준비 중 일부 PDF가 실패하면 새 모델 학습을 중단한다.
`training/local/failed_documents.json`의 실패 원인을 해결하고 다시 실행한다.
성공한 PDF의 라벨은 캐시하므로 동일한 파일에 매번 API를 호출하지 않는다.
PDF를 추가·수정하면 다시 train.py를 실행한다.
임시 라벨까지 새로 만들고 싶을 때만 `--force`를 사용한다.

### 지표 해석

GPT가 자동 생성한 라벨은 **사람이 검수한 정답이 아닌 silver label**이다.
이번 검증/테스트 지표는 분류기가 GPT 라벨을 얼마나 재현하는지를 측정한다.
실제 지원 자격 판단의 정확도나 실제 정답 대비 성능을 의미하지 않는다.
teacher의 잘못된 분류를 그대로 학습할 수 있으므로 실서비스 품질 판단에는 사람 검수 테스트셋이 필요하다.
정답 PDF·프로필 사례를 작성한 `evaluate.py`의 전체 판정 평가 기능도 유지했다.
기존 수동 조항 정답 양식과 `evaluate_parser.py`는 GPT 추출 자체의 별도 평가 기능이다.

## 4. 학습 후 Streamlit 실행

학습 완료 메시지가 나온 다음 실행한다.

```powershell
python -m streamlit run app.py
```

브라우저에서 새 PDF를 업로드하고 프로필을 입력한 뒤 분석한다.
서비스는 `models/clause_classifier.joblib`을 불러와 문장별 조항 유형을 예측한다.
Parser는 이 예측을 참고하면서 **새 PDF의 원문 자체**에서 자격·제출 서류·제외·제재·일정을 추출한다.
Pro/Critic/Writer가 해당 PDF와 신청자 프로필을 대조해 최종 보고서를 만든다.
다른 학습 PDF의 지원 조건을 새 PDF에 적용하지 않는다.

기본값은 학습 모델이 없으면 분석을 막고 학습 명령을 안내하는 것이다.
학습 없이 기존 GPT 분석만 사용하고 싶을 때에만 `.env`에 `REQUIRE_TRAINED_MODEL=false`를 설정한다.
OpenAI 모델 변경이나 앱 재실행만으로 기존 로컬 모델이 재학습되지는 않는다.

## 5. 사진의 원문 인용 오류 수정

원문 인용 검증 실패는 학습을 하지 않아서 생긴 오류가 아니다.
모델이 인용문을 요약하거나 PDF 인쇄 페이지 번호와 실제 페이지 번호를 혼동할 때 생길 수 있다.

수정한 Parser는:

- 전각 문자·유니코드 공백 등 표현 차이를 정규화해 비교한다. 숫자와 부정어는 유지한다.
- 인용문이 해당 입력 페이지에 실제 존재할 때만 페이지 번호를 교정한다.
- 틀린 인용문은 한 번 재추출한다.
- 계속 틀리면 원문에 줄 번호를 붙여 모델이 줄 번호만 고르게 하고, 코드는 실제 줄을 그대로 인용한다.
- 존재하지 않는 줄 번호나 인용문을 통과시키지 않는다.

OCR 오인식이나 원문 누락까지 모두 해결되는 것은 아니므로 스캔 결과는 여전히 원본 대조가 필요하다.
추출 경고가 남으면 보고서에서 추가 확인이 필요하다고 표시한다.

## 검증과 배포

테스트에서는 생성 PDF와 모의 GPT 라벨로 실제 sklearn 학습·모델 저장·불러오기·예측을 수행했다.
사용자 PC의 실제 데이터셋 학습이나 유료 API 호출을 여기서 수행한 상태는 아니다.

배포 서버에서도 모델 파일이 필요하다. 로컬에서 학습했다면 `models` 폴더를 운영 서버에 별도로 전달한다.
모델에는 학습된 특징이 들어 있으므로 데이터 공개 범위를 검토하고 관리한다.
기본 Git 제외 설정은 유지하며 키/원본/학습 기록을 자동 업로드하지 않는다.
