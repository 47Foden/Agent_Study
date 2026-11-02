"""Run: python -m streamlit run app.py"""
import hashlib
import hmac
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

import streamlit as st
from openai import OpenAI

from agents import AgentSystem, chunks, load_documents, markdown, pdf_pages

from pdf_utils import inspect_pdf, complete_ocr
from knowledge import load_index, search
from local_model import MODEL_PATH
from settings import load_server_config
st.set_page_config(page_title='공고핏 | 지원 전, 근거부터', page_icon='📋', layout='wide')


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


def bundle(results):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for number, result in enumerate(results, 1):
            archive.writestr(f'report_{number:03d}.md', markdown(result))
            archive.writestr(f'report_{number:03d}.json', json_bytes(result))
    return output.getvalue()


def profile_from_form(name, tech, qualifications, papers, additional):
    profile = {'신청자명': name.strip() or None,
               '보유 기술': tech.strip() or None,
               '자격 요건': qualifications.strip() or None,
               '보유 서류': papers.strip() or None,
               '추가 사실': additional.strip() or None}
    if not any(value is not None for value in profile.values()):
        raise ValueError('신청자 정보를 하나 이상 입력해 주세요.')
    return profile


with st.sidebar:
    st.title('📋 공고핏')
    st.caption('지원할 수 있는 이유와\n놓치기 쉬운 조건을 함께 살펴봅니다.')
    st.divider()
    st.subheader('분석 설정')
    try:
        try:
            server_secrets = dict(st.secrets)
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            server_secrets = {}
        config = load_server_config(server_secrets)
        api_key = config.api_key
        model, rounds = config.model, config.rounds
        if MODEL_PATH.is_file():
            st.success('학습된 조항 분류 모델 연결됨')
        elif config.require_trained_model:
            api_key = ''
            st.warning('먼저 터미널에서 python train.py --dataset "./데이터셋" 을 실행해 주세요.')
        if not config.api_key:
            st.warning('현재 분석 서비스를 준비 중입니다. 잠시 후 다시 이용해 주세요.')
        if config.password:
            entered = st.text_input('서비스 접속 비밀번호', type='password', key='access_password')
            if not hmac.compare_digest(entered.encode(), config.password.encode()):
                api_key = ''
                st.caption('비밀번호를 입력하면 분석할 수 있습니다.')
        st.caption('서류 정리 → 지원 근거 검토 → 위험 검토 → 최종 보고서')
    except (ValueError, OSError):
        api_key, model, rounds = '', 'gpt-4o-mini', 2
        st.error('서비스 설정을 확인 중입니다. 운영자에게 문의해 주세요.')
    if st.button('입력·결과 초기화', use_container_width=True):
        for key in list(st.session_state):
            del st.session_state[key]
        st.rerun()

st.caption('PDF 기반 지원 적격성 · 리스크 검토')
st.title('지원 전, 공고의 조건을 확인하세요.')
st.write('공고문과 신청자 정보를 대조해 지원 근거, 결격 위험, 보완할 내용을 정리합니다.')
st.info('PDF 한 개를 공고 한 건으로 분석합니다. 같은 공고의 본문과 별첨은 하나의 PDF로 합쳐 올려주세요.')

try:
    knowledge_index = load_index()
except (ValueError, OSError):
    knowledge_index = None
source_mode = st.radio('공고 선택 방식', ['PDF 직접 업로드', '등록된 데이터셋'], horizontal=True)
if source_mode == '등록된 데이터셋':
    if not knowledge_index or not knowledge_index['documents']:
        st.info('아직 등록된 공고가 없습니다. 운영자가 PDF 폴더로 build_dataset.py를 실행하면 표시됩니다.')
        st.stop()
    if st.session_state.get('source_mode') != source_mode:
        for key in ('results','failures','usage','run_profile'):
            st.session_state.pop(key, None)
    st.session_state['source_mode'] = source_mode
    st.session_state['prepared'] = [
        {'id':number,'name':doc['name'],'pages':{int(n):text for n,text in doc['pages'].items()},
         'warnings':doc['warnings'],'ocr_pages':[],'document_hash':doc['sha256']}
        for number,doc in enumerate(knowledge_index['documents'],1)]
    st.caption(f"등록된 공고 {len(knowledge_index['documents'])}개 · PDF를 다시 올릴 필요가 없습니다.")
else:
    if st.session_state.get('source_mode') == '등록된 데이터셋':
        for key in ('prepared','prepared_signature','upload_signature','results','failures','usage','run_profile'):
            st.session_state.pop(key, None)
    st.session_state['source_mode'] = source_mode
    upload = st.file_uploader('1. 공고 PDF 또는 데이터셋 ZIP 업로드', type=['pdf', 'zip'], key='dataset')
    if upload:
        if upload.size > 50 * 1024**2:
            st.error('업로드는 50MB 이하만 가능합니다.')
            st.stop()
        signature = hashlib.sha256(upload.getvalue()).hexdigest()
    else:
        signature = None
    if st.session_state.get('upload_signature') != signature:
        for key in ('prepared', 'prepared_signature', 'results', 'failures', 'usage', 'run_profile'):
            st.session_state.pop(key, None)
        st.session_state['upload_signature'] = signature

    if upload and st.session_state.get('prepared_signature') != signature:
        prepared, errors = [], []
        try:
            with TemporaryDirectory() as directory:
                source = Path(directory) / ('input.zip' if upload.name.lower().endswith('.zip') else 'input.pdf')
                source.write_bytes(upload.getvalue())
                documents = load_documents(source)
            with st.spinner('PDF 텍스트를 확인하고 있습니다…'):
                for index, (name, data) in enumerate(documents, 1):
                    if len(documents) == 1 and not upload.name.lower().endswith('.zip'):
                        name = upload.name
                    try:
                        pages, pending = inspect_pdf(data)
                        prepared.append({'id': index, 'name': name, 'pages': pages, 'warnings': [],
                                         'ocr_pages': pending, 'pdf_data': data,
                                         'document_hash':hashlib.sha256(data).hexdigest()})
                    except Exception as error:
                        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
                        errors.append(f'{name}: {reason}')
            st.session_state['prepared'] = prepared
            st.session_state['prepared_signature'] = signature
            for key in ('results', 'usage', 'run_profile'):
                st.session_state.pop(key, None)
            st.session_state['failures'] = errors
        except Exception as error:
            reason = str(error) if isinstance(error, ValueError) else type(error).__name__
            st.session_state['prepared_signature'] = signature
            st.session_state['failures'] = ['문서를 읽지 못했습니다: ' + reason]


prepared = st.session_state.get('prepared', [])
if not prepared:
    st.caption('PDF를 업로드하면 문서를 자동으로 읽습니다. 스캔 페이지는 분석 시작 시 자동으로 문자 인식합니다.')
else:
    st.success(f'문서 준비 완료 · {len(prepared)}개 공고')
    choices = {f"{p['id']:03d} · {p['name']}": p for p in prepared}
    selected = st.multiselect('분석할 공고 선택 (한 번에 최대 5개)', list(choices),
                             default=list(choices)[:1], max_selections=5, key='selected_docs')
    if selected:
        pending_total = sum(len(choices[key].get('ocr_pages', [])) for key in selected)
        if pending_total:
            st.info(f'스캔·이미지 확인이 필요한 페이지 {pending_total}개가 있습니다. 분석을 시작하면 자동으로 문자 인식합니다. 추가 API 사용료가 발생합니다.')
        with st.expander('자동 추출 텍스트 확인'):
            doc = choices[selected[0]]
            st.caption(doc['name'])
            for warning in doc['warnings']:
                st.warning(warning)
            page = st.selectbox('페이지', list(doc['pages']), key='preview_page')
            st.text_area('원문 추출 결과', doc['pages'][page] or '분석 시작 시 이 페이지를 문자 인식합니다.', height=220, disabled=True)
            st.download_button('추출 텍스트 다운로드', json_bytes({key: value for key, value in doc.items() if key != 'pdf_data'}),
                               'extracted_text.json', 'application/json')
        calls = sum(len(list(chunks(choices[key]['pages']))) + len(choices[key].get('ocr_pages', [])) + 2*rounds + 1 for key in selected)
        st.caption(f'현재 추출된 텍스트 기준 API 호출 추정: {calls}회 (OCR 후 늘어날 수 있음, 재시도 제외). 문서 길이에 따라 처리 시간이 달라집니다.')

st.subheader('2. 신청자 정보')
with st.form('applicant_form'):
    left, right = st.columns(2)
    with left:
        name = st.text_input('신청자 / 기업명', key='applicant_name')
        tech = st.text_area('보유 기술·경력', placeholder='예: Python, NLP / 개발 경력 3년', key='tech')
    with right:
        qualifications = st.text_area('자격 관련 정보', placeholder='기업 유형, 설립일, 지역, 나이, 학적 등', key='qualifications')
        papers = st.text_area('준비된 서류', placeholder='사업자등록증, 납세증명서 등', key='papers')
    additional = st.text_area('추가 사실·확인할 사항', placeholder='체납·제재 이력, 참여 가능 기간, 인증 등. 모르는 내용은 미확인으로 적어주세요.', key='additional')
    consent = st.checkbox('분석을 위해 선택한 PDF의 텍스트·페이지 이미지와 신청자 정보가 OpenAI API로 전송되는 데 동의합니다.', key='consent')
    submitted = st.form_submit_button('지원 적격성 분석 시작', type='primary',
                                      disabled=not prepared or not api_key, use_container_width=True)

if submitted:
    try:
        if not selected:
            raise ValueError('분석할 공고를 선택해 주세요.')
        if not model.strip():
            raise ValueError('GPT 모델명을 입력해 주세요.')
        if not consent:
            raise ValueError('데이터 전송 동의를 확인해 주세요.')
        profile = profile_from_form(name, tech, qualifications, papers, additional)
    except ValueError as error:
        st.error(str(error))
    else:
        st.session_state['results'] = []
        st.session_state['failures'] = []
        st.session_state['run_profile'] = profile
        status = st.status('에이전트가 분석을 준비하고 있습니다…', expanded=True)
        progress_bar = st.progress(0)
        def progress(message):
            status.update(label=message)
        system = AgentSystem(model.strip(), OpenAI(api_key=api_key, timeout=120, max_retries=2), progress=progress)
        system.parser_model = config.parser_model
        embedding_tokens = 0
        for count, label in enumerate(selected, 1):
            document = choices[label]
            with status:
                st.write(f"{count}/{len(selected)} · {document['name']}")
            try:
                if document.get('ocr_pages'):
                    complete_ocr(document['pdf_data'], document['pages'], document['ocr_pages'],
                                 system.ocr_page, warnings=document['warnings'])
                retrieved = []
                if knowledge_index and document.get('document_hash'):
                    retrieved, used_tokens = search(knowledge_index, json.dumps(profile, ensure_ascii=False) +
                        ' 신청 자격 제출 서류 제외 실격 가점 제재', system.client, document['document_hash'])
                    embedding_tokens += used_tokens
                result = system.run(document['name'], document['pages'], profile, document['warnings'], rounds, retrieved)
                st.session_state['results'].append(result)
            except Exception as error:
                reason = str(error) if isinstance(error, ValueError) else type(error).__name__
                st.session_state['failures'].append(f"{document['name']}: {reason}")
            progress_bar.progress(count / len(selected))
        st.session_state['usage'] = {**system.usage, 'embedding_tokens':embedding_tokens}
        status.update(label='분석 완료' if not st.session_state['failures'] else '분석 완료 · 실패한 문서 확인 필요',
                      state='complete' if st.session_state['results'] else 'error', expanded=False)

for error in st.session_state.get('failures', []):
    st.error(error)

results = st.session_state.get('results', [])
if results:
    st.divider()
    st.subheader('3. 분석 보고서')
    st.caption('아래 결과는 마지막으로 분석을 실행한 입력 기준입니다. 입력을 바꿨다면 다시 분석하세요.')
    metrics = st.columns(3)
    for col, label in zip(metrics, ['신청 가능', '신청 불가', '추가 확인 필요']):
        col.metric(label, sum(r['report']['status'] == label for r in results))
    st.download_button('전체 보고서 ZIP 다운로드', bundle(results), 'eligibility_reports.zip', 'application/zip')
    for number, result in enumerate(results, 1):
        st.markdown('### ' + result['document'])
        report_tab, clauses_tab, debate_tab = st.tabs(['최종 보고서', '추출 조항', 'Pro · Critic 토론'])
        with report_tab:
            st.markdown(markdown(result))
            st.download_button('보고서 Markdown 다운로드', markdown(result), f'report_{number}.md',
                               'text/markdown', key=f'md_{number}')
            st.download_button('전체 분석 JSON 다운로드', json_bytes(result), f'report_{number}.json',
                               'application/json', key=f'json_{number}')
        with clauses_tab:
            if result.get('retrieved_context'):
                with st.expander('프로필과 관련된 검색 근거'):
                    for hit in result['retrieved_context']:
                        st.caption(f"{hit['source']} · p.{hit['page']}")
                        st.text(hit['text'])
            for cid, clause in result['clauses'].items():
                with st.expander(f"{cid} · {clause['category']} · {clause['summary']}"):
                    for evidence in clause['evidence']:
                        st.caption(f"PDF p.{evidence['page']}")
                        st.text(evidence['quote'])
        with debate_tab:
            for turn in result['debate']:
                st.markdown(f"**{turn['round']}회차 · {turn['role']}**")
                for claim in turn['result']['claims']:
                    st.write(f"[{claim['assessment']}] {claim['conclusion']}")
                    st.caption('근거: ' + ', '.join(claim['clause_ids']))
                    st.caption('대응 대상: ' + claim['response_to'])
                for question in turn['result']['missing_information']:
                    st.warning(question)
    with st.expander('이번 실행의 입력·사용량'):
        st.json(st.session_state.get('run_profile', {}))
        st.json(st.session_state.get('usage', {}))

st.divider()
st.caption('인용문과 원문 페이지를 확인한 뒤 최종 지원 여부를 결정하세요. 스캔 PDF는 자동 문자 인식하며, 판독 결과를 원본과 대조해 주세요. '
           '업로드·결과는 현재 세션 메모리에서 처리하며 영구 저장하지 않습니다. 필요한 보고서는 다운로드하세요.')
