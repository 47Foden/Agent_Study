# 공고핏

공고문 PDF와 신청자 정보를 대조하여 지원 근거와 결격 위험을 검토하는 다중 에이전트 연구 프로젝트다.

## 에이전트 구성

| 에이전트 | 역할 |
| --- | --- |
| Parser | 신청 자격·제출 서류·제외 대상·제재 조항을 원문 근거와 함께 추출한다. |
| Pro | 신청자 정보에 기반한 지원 가능 근거와 가점을 검토한다. |
| Critic | Pro의 주장을 반박하고 결격 사유와 위험을 검토한다. |
| Writer | 토론을 종합하여 적격성 및 리스크 보고서를 작성한다. |

## 연구의 한계

- 본 연구는 사전 학습된 LLM을 활용한 역할 분담과 적대적 상호 검토에 초점을 둔다. LLM 자체의 가중치를 학습하거나 학습 전후 LLM 성능을 비교한 연구는 아니다.
- 별도로 학습한 TF-IDF 및 로지스틱 회귀 모델은 조항 유형 분류를 돕는다. 최종 적격성 판정과 보고서 생성은 LLM 호출에 의존한다.
- GPT가 생성한 임시 라벨을 사용한 분류기 평가 결과는 사람의 정답에 대한 최종 적격성 정확도로 해석할 수 없다.
- 장문 PDF 분할 처리, 스캔 문서 OCR, 인용 검증 재요청, 순차적인 토론으로 응답 지연과 API 비용이 발생한다.
- 신청자 정보가 부족하거나 주장의 근거 연결이 잘못되면 검증 단계에서 분석이 중단될 수 있다. 정보 부족을 ‘추가 확인 필요’로 처리하는 안정성 개선이 필요하다.
- 단일 LLM 대비 효과는 사람이 검토한 독립 테스트 케이스로 판정 정확도, 결격 사유 탐지율, 근거 정확성, 처리 시간 및 비용을 비교하여 검증해야 한다. 검증되지 않은 성능 향상을 주장하지 않는다.
- 결과는 지원 의사결정의 참고 자료이며 공고 원문과 담당 기관의 안내를 확인해야 한다.

## Streamlit 별도 배포

**배포 상태: 공개 서비스 URL 미등록. 아래 링크는 실행 중인 앱이 아닌 배포 관리 페이지다.**

[Streamlit Community Cloud에서 배포 설정](https://share.streamlit.io/)

Create app에서 다음 값을 입력한다.

| 항목 | 값 |
| --- | --- |
| Repository | 47Foden/Agent_Study |
| Branch | main |
| Main file path | eligibility_agents/app.py |
| Custom subdomain | gonggofit-47foden (사용 가능할 때 선택) |

Advanced settings의 Secrets에는 OPENAI_API_KEY와 사용 가능한 OPENAI_MODEL을 설정한다. API 키를 README나 코드에 입력하지 않는다.

배포 서버에도 eligibility_agents/models/clause_classifier.joblib을 제공해야 한다. 로컬 모델과 데이터셋은 자동 업로드되지 않는다. 모델 없이 GPT만 사용하는 데모를 의도적으로 운영할 경우에만 Secrets에 REQUIRE_TRAINED_MODEL = false를 설정한다. 이 모드는 학습 모델을 사용하는 실험과 구분한다.

배포가 성공하면 Cloud가 표시하는 실제 https://...streamlit.app 주소를 이 README에 추가한다. 위 희망 도메인은 예약되거나 생성된 주소가 아니다.

- [공식 배포 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [실행 및 배포 문서](eligibility_agents/DEPLOY.md)
- [연구 설계](docs/AGENTS.md)
