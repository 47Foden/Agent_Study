import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace
from pathlib import Path
from streamlit.testing.v1 import AppTest
from agents import Claim, Clause, Evidence, Extraction, Debate, Report

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class StreamlitTest(unittest.TestCase):
    def make_app(self, prepared=False):
        app = AppTest.from_file(APP, default_timeout=15)
        app.secrets['OPENAI_API_KEY'] = 'fake-server-key'
        app.secrets['REQUIRE_TRAINED_MODEL'] = 'false'
        app.secrets['APP_PASSWORD'] = 'test-password'
        app.run()
        if prepared:
            app.session_state['prepared'] = [{'id': 1, 'name': 'test.pdf',
                'pages': {1: '중소기업만 신청할 수 있다.'}, 'warnings': []}]
            app.run()
        return app

    def test_initial_page_and_missing_upload(self):
        app = self.make_app()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(next(b for b in app.button if b.label == '지원 적격성 분석 시작').disabled)

    def test_server_key_requires_password(self):
        app = self.make_app(True)
        self.assertTrue(next(b for b in app.button if b.label == '지원 적격성 분석 시작').disabled)
        app.text_input(key='access_password').set_value('wrong').run()
        self.assertTrue(next(b for b in app.button if b.label == '지원 적격성 분석 시작').disabled)
        app.text_input(key='access_password').set_value('test-password').run()
        self.assertFalse(next(b for b in app.button if b.label == '지원 적격성 분석 시작').disabled)
        self.assertEqual(len(app.exception), 0)

    def test_validation_prevents_api_without_consent(self):
        app = self.make_app(True)
        app.text_input(key='access_password').set_value('test-password').run()
        next(b for b in app.button if b.label == '지원 적격성 분석 시작').click().run()
        self.assertTrue(any('동의' in error.value for error in app.error))
        self.assertEqual(len(app.exception), 0)

    def test_report_render_and_rerun_does_not_call_api(self):
        app = self.make_app(True)
        app.text_input(key='access_password').set_value('test-password').run()
        app.text_input(key='applicant_name').set_value('테스트 기업')
        app.text_area(key='qualifications').set_value('중소기업')
        app.checkbox(key='consent').check()
        clause = Clause(category='신청 자격', summary='중소기업 대상',
                        evidence=[Evidence(page=1, quote='중소기업만 신청할 수 있다.')])
        claim = Claim(conclusion='중소기업 조건 충족', clause_ids=['C0001'],
                      profile_keys=['자격 요건'], assessment='충족', response_to='최초 검토')
        debate = Debate(claims=[claim], missing_information=[])
        report = Report(status='신청 가능', summary='자격 확인', fatal_disqualifications=[],
                        positive_factors=[claim], improvements=[], unresolved_questions=[])
        values = [Extraction(clauses=[clause], uncertainties=[]), debate, debate, debate, debate, report]
        client = Mock()
        client.responses.parse.side_effect = [SimpleNamespace(output_parsed=value,
            usage=SimpleNamespace(input_tokens=1, output_tokens=1)) for value in values]
        with patch('openai.OpenAI', return_value=client):
            next(b for b in app.button if b.label == '지원 적격성 분석 시작').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.session_state['results']), 1)
            self.assertEqual(client.responses.parse.call_count, 6)
            app.run()
            self.assertEqual(client.responses.parse.call_count, 6)
            self.assertEqual(len(app.exception), 0)


if __name__ == '__main__':
    unittest.main()
