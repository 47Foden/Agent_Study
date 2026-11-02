"""Pro Agent와 Critic Agent: 서로 다른 역할의 검토와 반박."""
from schemas import Debate
from validation import validate_claims

PRO_PROMPT = """Pro Agent다. 지원 가능 근거와 가점 요인을 찾는다.
이전 Critic 반박에 응답하고 오류는 철회한다. clause_ids와 profile_keys는
제공된 키를 정확히 사용한다. 확인되지 않은 사항은 미확인으로 표시한다.
response_to에는 반박 대상 주장을 요약한다. 첫 회는 최초 검토라고 적는다."""

CRITIC_PROMPT = """Critic Agent다. Pro 주장을 원문에 대조해 반박한다.
신청 불가, 실격, 제출 누락, 일정, 지체상금, 환수/제재를 집중 검토한다.
숨어 있는 조건을 original_pages에서 다시 검색하듯 전수 검토한다.
일반적 위험과 신청자에게 확인된 불충족을 구분한다. 근거 없는 반박을 만들지 않는다.
새로 발견한 미추출 조건은 missing_information에 원문 페이지와 함께 적고
최종 추가 확인을 요구한다. 주장의 clause_ids와 profile_keys는 실제 키만 쓴다."""

class ProAgent:
    prompt = PRO_PROMPT
    def __init__(self, ask):
        self.ask = ask

    def run(self, payload, transcript):
        result = self.ask(self.prompt, {**payload, 'debate': transcript}, Debate)
        validate_claims(result.claims, set(payload['clauses']), payload['profile'])
        return result

class CriticAgent(ProAgent):
    prompt = CRITIC_PROMPT

class ProCritiqueAgents:
    def __init__(self, ask):
        self.pro = ProAgent(ask)
        self.critic = CriticAgent(ask)

    def run(self, payload, rounds=2):
        transcript = []
        for turn in range(rounds):
            for role, agent in [('Pro', self.pro), ('Critic', self.critic)]:
                result = agent.run(payload, transcript)
                transcript.append({'round': turn+1, 'role': role, 'result': result.model_dump()})
        return transcript
