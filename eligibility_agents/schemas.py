"""에이전트 간 공유하는 구조화 데이터 형식."""
from typing import Literal
from pydantic import BaseModel, ConfigDict

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Evidence(StrictModel):
    page: int
    quote: str

class Clause(StrictModel):
    category: Literal['신청 자격', '제출 서류', '신청 제외 대상', '제재 조항', '가점', '일정', '기타']
    summary: str
    evidence: list[Evidence]

class Extraction(StrictModel):
    clauses: list[Clause]
    uncertainties: list[str]

class Claim(StrictModel):
    conclusion: str
    clause_ids: list[str]
    profile_keys: list[str]
    assessment: Literal['충족', '불충족', '미확인', '일반 위험']
    response_to: str

class Debate(StrictModel):
    claims: list[Claim]
    missing_information: list[str]

class Report(StrictModel):
    status: Literal['신청 가능', '신청 불가', '추가 확인 필요']
    summary: str
    fatal_disqualifications: list[Claim]
    positive_factors: list[Claim]
    improvements: list[str]
    unresolved_questions: list[str]
