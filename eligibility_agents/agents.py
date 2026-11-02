"""공고핏 실행 조율 및 CLI. 웹 서비스는 app.py로 실행한다."""
import argparse
import json
import os
from datetime import date
from pathlib import Path
from openai import OpenAI
from schemas import Evidence, Clause, Extraction, Claim, Debate, Report
from validation import normalized, validate_claims, validate_evidence
from pdf_utils import pdf_pages, load_documents, chunks
from llm_client import LLMClient
from parser import ParserAgent
from procritique import ProCritiqueAgents
from writer import WriterAgent
from settings import load_server_config

class AgentSystem(LLMClient):
    """에이전트 실행 순서와 데이터 전달만 조율한다."""
    def run(self, name, pages, profile, warnings, rounds=2, retrieved_context=None):
        if rounds not in (1, 2, 3):
            raise ValueError('토론 횟수는 1~3이어야 한다')
        clauses, uncertainties = ParserAgent(self.ask).run(pages)
        payload = {'document': name, 'today': date.today().isoformat(),
                   'profile': profile, 'clauses': clauses,
                   'original_pages': [{'page': n, 'text': text} for n, text in pages.items()],
                   'extraction_warnings': warnings + uncertainties,
                   'retrieved_context': retrieved_context or []}
        if len(json.dumps(payload, ensure_ascii=False)) > 180000:
            raise ValueError('검토 입력이 18만 자를 초과한다. 공고를 관련 별첨과 함께 나눠 입력하라')
        transcript = ProCritiqueAgents(self.ask).run(payload, rounds)
        report = WriterAgent(self.ask).run(payload, transcript)
        return {'document': name, 'model': self.model, 'profile': profile,
                'clauses': clauses, 'warnings': warnings + uncertainties,
                'debate': transcript, 'report': report.model_dump(),
                'retrieved_context': retrieved_context or []}


def markdown(result):
    r = result['report']
    lines = [f"# {result['document']}", '', f"**판정: {r['status']}**", '', r['summary']]
    for heading, key in [('치명적 결격 사유 (최대 3개)', 'fatal_disqualifications'),
                         ('지원 가능 근거 및 가점', 'positive_factors')]:
        lines += ['', '## ' + heading, '']
        if not r[key]:
            lines.append('확인된 항목 없음 (자격 충족을 뜻하지 않음).')
        for claim in r[key]:
            lines.append(f"- [{claim['assessment']}] {claim['conclusion']}")
            lines.append('  - 프로필 근거: ' + ', '.join(claim['profile_keys']))
            for cid in claim['clause_ids']:
                clause = result['clauses'][cid]
                for e in clause['evidence']:
                    lines.append(f"  - {cid}, PDF p.{e['page']}: {e['quote']}")
    for heading, items in [('보완 필요 사항', r['improvements']),
                           ('추가 확인 질문', r['unresolved_questions']),
                           ('추출 한계', result['warnings'])]:
        lines += ['', '## ' + heading, ''] + ['- ' + i for i in items]
        if not items:
            lines.append('없음')
    return '\n'.join(lines) + '\n'

def main():
    config = load_server_config()
    parser = argparse.ArgumentParser(description='Parser → Pro ↔ Critic → Writer')
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--output', type=Path, default=Path('outputs'))
    parser.add_argument('--model', default=config.model)
    parser.add_argument('--rounds', type=int, choices=[1, 2, 3], default=2)
    parser.add_argument('--extract-only', action='store_true', help='API 없이 PDF 텍스트만 추출')
    args = parser.parse_args()
    if not args.extract_only and (not args.profile or not config.api_key):
        parser.error('--profile과 OPENAI_API_KEY가 필요하다')
    profile = json.loads(args.profile.read_text(encoding='utf-8-sig')) if args.profile else {}
    if not isinstance(profile, dict) or (not args.extract_only and not profile):
        parser.error('프로필은 비어 있지 않은 JSON 객체여야 한다')
    args.output.mkdir(parents=True, exist_ok=True)
    system = None if args.extract_only else AgentSystem(args.model, OpenAI(api_key=config.api_key, timeout=120, max_retries=2))
    if system:
        system.parser_model = config.parser_model
    failures = []
    try:
        documents = load_documents(args.input)
    except Exception as error:
        parser.exit(1, f'입력 오류: {error}\n')
    for index, (name, data) in enumerate(documents, 1):
        stem = args.output / f'document_{index:03d}'
        print(f'[{index}/{len(documents)}] {name}', flush=True)
        try:
            pages, warnings = pdf_pages(data, system.ocr_page if system else None)
            stem.with_suffix('.text.json').write_text(json.dumps(
                {'document': name, 'pages': pages, 'warnings': warnings}, ensure_ascii=False, indent=2), encoding='utf-8')
            if system:
                result = system.run(name, pages, profile, warnings, args.rounds)
                stem.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                stem.with_suffix('.md').write_text(markdown(result), encoding='utf-8')
        except Exception as error:
            # Do not echo raw API errors which may include submitted content.
            reason = str(error) if isinstance(error, ValueError) else type(error).__name__
            failures.append({'document': name, 'error': reason})
            print(f'실패: {name}: {reason}', flush=True)
    summary = {'failed': failures, 'documents': len(documents),
               'usage': system.usage if system else {}}
    (args.output / 'run_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if failures else 0

if __name__ == '__main__':
    raise SystemExit(main())
