"""Writer Agent: 근거를 수합하여 최종 적격성 보고서 작성."""
from schemas import Report
from validation import validate_claims

PROMPT = """Writer Agent다. 토론을 중립적으로 종합한다.
신청 가능 여부, 치명적 결격 사유 최대 3개, 긍정적 근거, 보완사항을 작성한다.
결격 사유가 3개 미만이면 채우려고 만들지 않는다. fatal_disqualifications에는
신청자에게 실제 적용되는 불충족만 넣는다. 단순 위험/정보 부족은 넣지 않는다.
모든 필수 자격 충족을 확인하지 못하거나 원문/프로필 누락, 토론의 미해결 쟁점이
있으면 추가 확인 필요다. 명확한 결격이 확인되면 신청 불가다.
각 근거에 유효한 clause_ids와 profile_keys를 쓴다."""

class WriterAgent:
    def __init__(self, ask):
        self.ask = ask

    def run(self, payload, transcript):
        report = self.ask(PROMPT, {**payload, 'debate': transcript}, Report)
        ids = set(payload['clauses'])
        profile = payload['profile']
        warnings = payload['extraction_warnings']
        validate_claims(report.fatal_disqualifications + report.positive_factors, ids, profile)
        if len(report.fatal_disqualifications) > 3:
            raise ValueError('결격 사유가 3개를 초과함')
        if any(c.assessment != '불충족' for c in report.fatal_disqualifications):
            raise ValueError('확인되지 않은 결격 판정')
        if report.fatal_disqualifications:
            report.status = '신청 불가'
        elif report.status == '신청 불가':
            raise ValueError('근거 없는 신청 불가 판정')
        missing = [item for turn in transcript for item in turn['result']['missing_information']]
        if (warnings or missing or report.unresolved_questions) and report.status == '신청 가능':
            report.status = '추가 확인 필요'
        return report
