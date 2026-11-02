import io
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from pathlib import Path
import pymupdf
from streamlit.testing.v1 import AppTest
from pdf_utils import inspect_pdf, complete_ocr
from ocr import OCRPage, extract_page


def sample_pdf(scanned=False):
    with pymupdf.open() as source:
        page = source.new_page()
        page.insert_text((72,72), 'Applicants must be students. Tax penalties exclude applicants.')
        if not scanned:
            return source.tobytes()
        png = page.get_pixmap().tobytes('png')
    with pymupdf.open() as scanned_doc:
        scanned_doc.new_page().insert_image(pymupdf.Rect(0,0,595,842), stream=png)
        return scanned_doc.tobytes()


class PDFOCRTest(unittest.TestCase):
    def test_native_pdf_no_ocr(self):
        pages, pending = inspect_pdf(sample_pdf())
        self.assertIn('students', pages[1])
        self.assertEqual(pending, [])

    def test_scanned_pdf_detects_and_automatically_transcribes(self):
        data = sample_pdf(True)
        pages, pending = inspect_pdf(data)
        self.assertEqual(pending, [1])
        recognize = Mock(return_value=OCRPage(text='학생만 신청할 수 있다.', is_blank=False, uncertainties=[]))
        warnings = complete_ocr(data, pages, pending, recognize)
        self.assertEqual(pages[1], '학생만 신청할 수 있다.')
        self.assertEqual(pending, [])
        self.assertTrue(warnings)
        self.assertTrue(recognize.call_args.args[0].startswith(b'\x89PNG'))
        complete_ocr(data, pages, pending, recognize)
        self.assertEqual(recognize.call_count, 1)

    def test_mixed_pdf_keeps_original_page_numbers(self):
        with pymupdf.open(stream=sample_pdf(), filetype='pdf') as doc:
            with pymupdf.open(stream=sample_pdf(True), filetype='pdf') as scan:
                doc.insert_pdf(scan)
            data = doc.tobytes()
        pages, pending = inspect_pdf(data)
        self.assertEqual(pending, [2])
        complete_ocr(data, pages, pending, lambda image, number:
                     OCRPage(text='제외 조항', is_blank=False, uncertainties=[]))
        self.assertIn('students', pages[1])
        self.assertEqual(pages[2], '제외 조항')

    def test_ocr_payload_and_incomplete_response(self):
        client = Mock()
        client.responses.parse.return_value = SimpleNamespace(
            output_parsed=OCRPage(text='지원 자격', is_blank=False, uncertainties=[]), usage=None)
        result, usage = extract_page(client, 'mock-model', b'png')
        params = client.responses.parse.call_args.kwargs
        self.assertFalse(params['store'])
        self.assertEqual(params['input'][1]['content'][1]['type'], 'input_image')
        client.responses.parse.return_value.output_parsed = None
        with self.assertRaises(ValueError):
            extract_page(client, 'mock-model', b'png')

    def test_upload_prepares_automatically_without_api(self):
        data = sample_pdf(True)
        uploaded = SimpleNamespace(size=len(data), name='scan.pdf', getvalue=lambda:data)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'))
        app.secrets['OPENAI_API_KEY'] = 'test-key-not-real'
        with patch('streamlit.file_uploader', return_value=uploaded), patch('openai.OpenAI') as api:
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state['prepared'][0]['ocr_pages'], [1])
            self.assertFalse(any('문서 확인' in b.label for b in app.button))
            self.assertFalse(any('예산' in widget.label for widget in app.text_input))
            app.run()
            api.assert_not_called()
            self.assertEqual(len(app.exception), 0)
