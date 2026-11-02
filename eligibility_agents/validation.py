"""원문 인용과 신청자 근거 검증."""
import re
import unicodedata
from schemas import Extraction, Claim

def normalized(text: str) -> str:
    text = unicodedata.normalize('NFKC', text)
    text = re.sub('[\u200b\u200c\u200d\ufeff\u00ad]', '', text)
    return re.sub(r'\s+', '', text)

def validate_evidence(extraction: Extraction, pages: dict[int, str]) -> None:
    for clause in extraction.clauses:
        if not clause.evidence:
            raise ValueError('근거 없는 조항이 반환됨')
        for evidence in clause.evidence:
            if (not normalized(evidence.quote) or evidence.page not in pages
                    or normalized(evidence.quote) not in normalized(pages[evidence.page])):
                raise ValueError(f'원문 인용 검증 실패: p.{evidence.page}')

def validate_claims(claims: list[Claim], ids: set[str], profile: dict) -> None:
    for claim in claims:
        if not claim.clause_ids or not set(claim.clause_ids) <= ids:
            raise ValueError('주장의 조항 ID가 없거나 존재하지 않음')
        if not set(claim.profile_keys) <= set(profile):
            raise ValueError('존재하지 않는 신청자 정보 참조')
        if claim.assessment in ('충족', '불충족') and not claim.profile_keys:
            raise ValueError('신청자 정보 없이 충족/불충족 판정')
