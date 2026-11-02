# 현재 기본 학습 경로 안내

신규 OpenAI 사용자는 아래 문서의 유료 파인튜닝 경로를 실행할 수 없다.
현재 기본 경로는 [TRAIN_FIRST.md](TRAIN_FIRST.md)의 로컬 `train.py`다.
아래 RAG/평가 안내는 유지하며, OpenAI 파인튜닝 부분은 기존 이용 자격을 가진 고객을 위한 레거시 경로다.

# 데이터셋 활용, 실제 학습, 테스트와 API 키

## 무엇이 달라졌나

기존 서비스는 사전 학습된 GPT의 추론만 사용했다.
현재는 PDF 폴더를 지식 색인으로 만들어 검색하는 RAG와,
사람이 정답을 검수한 뒤 실제 Parser 모델을 파인튜닝하는 경로를 모두 제공한다.
RAG는 PDF 내용을 검색할 수 있게 만드는 것이며 GPT 가중치를 바꾸지 않는다.
파인튜닝은 입력과 올바른 출력 예시로 GPT 가중치를 조정하는 실제 학습이다.

PDF만 넣으면 무엇이 정답인지 알 수 없으므로 적격 판정이나 조항 추출을 자동으로 지도학습할 수 없다.
GPT가 만든 답을 그대로 정답으로 사용하거나 학습 결과로 포장하지 않는다.
학습 예시, 검증 예시, 테스트 정답은 사람이 확인해야 한다.

## 1. API 키 설정·확인

`app.py`와 같은 폴더의 `.env`를 열고 아래 값을 설정한다.
기존 `.env`가 있으면 덮어쓰지 말고 필요한 값만 수정한다.
`.env.example`에 키를 넣었던 이전 버전은 시작 시 `.env`로 이전한다.
처음 설치해 키 파일이 없다면 `.env.template`을 복사해 `.env`를 만든다.

```dotenv
OPENAI_API_KEY=실제_API키
OPENAI_MODEL=gpt-4o-mini
APP_PASSWORD=
DEBATE_ROUNDS=2
OPENAI_PARSER_MODEL=
```

키 값을 화면이나 로그로 출력하지 않고 실제 API 호출로 확인한다.
프로젝트 폴더에서 가상환경을 활성화한 상태로 실행한다.

```powershell
python check_api.py --embeddings
```

`API 연결 성공: 설정된 모델이 응답했습니다.`가 나오면 모델과 임베딩 API 연결이 성공한 것이다.
이 확인에도 소량의 API 비용이 발생한다.
AuthenticationError는 키, PermissionDeniedError는 권한,
RateLimitError는 결제·사용 한도·속도 제한을 확인한다.
키를 복사해 채팅에 보내거나 GitHub에 올리지 않는다.

## 2. PDF 폴더를 서비스의 데이터셋으로 등록 (RAG)

`eligibility_agents` 안에 있는 PDF 폴더를 그대로 사용한다. 예를 들어 `데이터셋` 폴더라면:

```powershell
python build_dataset.py --dataset ".\데이터셋"
```

폴더 이름이 `dataset`이라면:

```powershell
python build_dataset.py --dataset ".\dataset"
```

`--dataset`을 생략하면 `dataset`, `datasets`, `데이터셋` 중 PDF가 있는 폴더를 찾는다.
둘 이상이면 사용할 폴더를 명시해야 한다. 하위 폴더의 PDF도 포함한다.

처리 과정은 PDF 읽기 → 필요 시 OCR → 페이지별 텍스트 분할 → OpenAI 임베딩 → 로컬 색인 저장이다.
결과는 `knowledge_base/index.json`에 저장한다. 이미 처리한 동일 파일은 재사용한다.
PDF를 추가·수정·삭제하면 위 명령을 다시 실행한다. 전체 재구축은 `--force`를 붙인다.
일부 파일이 실패하면 요약에 표시하고 성공한 문서만 색인한다. 실패한 옛 버전은 새 색인에 남기지 않는다.
전체 실패 시 기존 색인은 유지하므로 실패 원인을 해결하고 다시 실행해야 한다.

PDF 텍스트/스캔 이미지는 OCR 및 임베딩을 위해 OpenAI API로 전송되며 비용이 발생한다.
색인에는 원문과 벡터가 들어 있지만 API 키는 들어 있지 않다.

이제 서비스를 실행한다.

```powershell
python -m streamlit run app.py
```

화면에서 **등록된 데이터셋** → 분석할 공고 선택 → 프로필 입력 → 분석 시작을 누른다.
PDF를 다시 업로드할 필요가 없다.
프로필과 관련된 조항을 벡터 검색해 Pro/Critic/Writer의 참고 근거로 전달한다.
검색이 제외 조항을 놓칠 수 있으므로 Parser는 선택 공고의 원문 전체도 검토한다.
다른 공고의 자격이나 제재 조항을 섞지 않도록 검색은 선택한 공고로 한정한다.
이 구조는 PDF를 외우도록 학습시키는 방식이 아니다.

## 3. 진짜 Parser 학습용 정답 작성

실제 파인튜닝을 원할 때만 아래 과정을 진행한다.

```powershell
python train_parser.py init-labels
```

`training/labels.jsonl`에 색인의 페이지 텍스트를 담은 정답 양식이 생성된다.
파일의 각 줄은 한 학습 예시다. 기존 정답 파일은 자동으로 덮어쓰지 않는다.
각 예시의 `expected_extraction`을 사람이 작성하고 `reviewed`를 true로 바꾼다.
형식 예시는 다음과 같다. 아래 텍스트는 실제 데이터가 아닌 형식 설명용이다.

```json
{
  "document": "공고.pdf",
  "document_hash": "양식에_이미_있는_해시_유지",
  "page": 1,
  "text": "재학생만 신청할 수 있다. 휴학생은 신청할 수 없다.",
  "reviewed": true,
  "expected_extraction": {
    "clauses": [
      {
        "category": "신청 자격",
        "summary": "재학생 대상",
        "evidence": [{"page": 1, "quote": "재학생만 신청할 수 있다."}]
      },
      {
        "category": "신청 제외 대상",
        "summary": "휴학생 제외",
        "evidence": [{"page": 1, "quote": "휴학생은 신청할 수 없다."}]
      }
    ],
    "uncertainties": []
  }
}
```

실제 JSONL에서는 한 예시를 한 줄로 저장한다. 페이지 번호와 인용문은 실제 PDF에서 확인한다.
해당 페이지에 핵심 조항이 없다면 검수 후 clauses를 빈 배열로 둘 수 있다.
입력 텍스트는 예시당 최대 12000자이며 넘으면 같은 문서 해시를 유지한 채 적절히 나눠 작성한다.
판독 불가한 OCR 텍스트는 원본 PDF와 대조해 바로잡고 정답도 함께 검수한다.

## 4. 학습·검증·테스트 분리와 실제 파인튜닝

```powershell
python train_parser.py prepare
```

같은 PDF 해시가 서로 다른 분할에 들어가지 않게 문서 단위로 약 80/10/10으로 나눈다.
서로 다른 문서가 최소 3개 필요하며 소규모 자료는 검증/테스트 문서를 최소 한 개씩 확보한다.
동일 입력이 서로 다른 분할에 있으면 중복을 정리하도록 중단한다.
분할 결과는 `training/split_manifest.json`에 남긴다.
train.jsonl은 학습, validation.jsonl은 학습 중 검증, test.jsonl은 보류한 최종 평가용이다.
테스트 정답을 보며 프롬프트나 모델을 반복 조정했다면 새로운 보류 테스트셋을 준비해야 한다.

파인튜닝을 지원하고 계정에서 사용 가능한 모델 ID를 확인한 뒤 실행한다.
아래 MODEL_ID는 실제 지원 모델 ID로 바꿔야 한다.

```powershell
python train_parser.py start --base-model "MODEL_ID" --eligible-existing-customer
```

**이 명령은 실제 유료 파인튜닝 작업을 제출한다.**
학습 예시는 최소 10개가 필요하고, 예시가 적으면 품질 개선이 보장되지 않는다.
PDF만 넣은 상태나 미검수 정답으로는 실행할 수 없다.
지원 모델, 요금, 계정 권한은 OpenAI의 현재 파인튜닝 문서를 확인한다.

반환된 작업 ID로 상태를 확인한다.

```powershell
python train_parser.py status --job-id "ftjob-반환된작업ID"
```

완료된 `fine_tuned_model` 값을 `.env`에 넣고 서비스를 재시작한다.

```dotenv
OPENAI_PARSER_MODEL=ft:실제로_반환된_모델ID
```

Parser만 이 모델을 사용한다. OCR/Pro/Critic/Writer는 OPENAI_MODEL을 유지한다.
파인튜닝한 모델도 현재 API의 Structured Outputs를 지원해야 한다.

## 5. 테스트 데이터로 성능 비교

동일한 보류 test.jsonl을 사용해 학습 전/후 Parser를 각각 평가한다.

```powershell
python evaluate_parser.py --model "gpt-4o-mini" --output evaluation/baseline.json
python evaluate_parser.py --model "ft:실제모델ID" --output evaluation/finetuned.json
```

엄밀한 학습 효과 비교에는 학습에 사용한 원본 base-model을 baseline으로 지정한다.
두 명령의 test.jsonl과 평가 기준을 동일하게 유지한다.
측정값은 조항 유형+페이지+공백 제거 인용문에 대한 exact-match precision/recall/F1이다.
요약 표현의 의미적 유사도나 전체 적격 판정 정확도를 의미하지 않는다.
인용문을 더 길게 잡아도 exact-match에서는 불일치일 수 있다.

전체 에이전트의 최종 적격 판정도 별도로 평가한다.
`evaluation_cases.template.jsonl`을 복사해 실제 문서·프로필·사람이 판정한 정답을 작성한다.
expected_status는 신청 가능/신청 불가/추가 확인 필요 중 하나다. reviewed=true로 검수한다.

```powershell
python evaluate.py --dataset ".\데이터셋" --cases ".\내_테스트사례.jsonl"
```

결과는 `evaluation/eligibility_metrics.json`에 정확도와 실패 내역으로 저장한다.
실패 사례도 정확도 계산의 전체 분모에 포함한다.
Parser 분할 manifest가 있다면 학습/검증 문서와 겹치는 테스트 공고는 거부한다.
최종 보고서 내용 전체의 정확성까지 자동 채점하지는 않는다.

## 검증 범위와 배포

이 ZIP에는 실제 사용자 PDF·키·정답·학습 결과가 없다.
사용자 PC 폴더는 이 대화에서 직접 읽을 수 없어 실제 색인/학습/테스트 지표를 생성하지 않았다.
모의 API로 색인 저장·재사용·검색·문서별 분리·평가 계산·화면 연결을 검증했다.

로컬 데이터셋, 색인, 학습·평가 결과는 기본적으로 Git에서 제외된다.
Streamlit Cloud에서는 로컬 PC의 파일을 직접 읽지 못한다.
서버에 PDF와 색인을 별도로 제공해야 하며, 공개 공고만 담은 색인을 의도적으로 배포하려면
자료 공개 범위를 검토한 뒤 운영자가 배포 경로를 구성해야 한다.

공식 참고:
https://developers.openai.com/api/docs/guides/embeddings
https://developers.openai.com/api/docs/guides/supervised-fine-tuning
