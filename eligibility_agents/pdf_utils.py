"""PDF/ZIP 읽기 및 텍스트 분할."""
import zipfile
from pathlib import Path
from validation import normalized

def inspect_pdf(data):
    """로컬 추출만 수행한다. OCR이 필요한 페이지를 표시하며 외부 전송은 하지 않는다."""
    import pymupdf
    try:
        document = pymupdf.open(stream=data, filetype='pdf')
    except Exception:
        raise ValueError('PDF를 열 수 없습니다. 손상 여부 또는 파일 형식을 확인해 주세요.') from None
    with document:
        if document.needs_pass:
            raise ValueError('암호화 PDF는 암호를 해제한 후 입력해야 합니다.')
        if not 0 < len(document) <= 500:
            raise ValueError('PDF는 1~500페이지만 지원합니다.')
        pages, pending = {}, []
        for number, page in enumerate(document, 1):
            text = page.get_text('text', sort=True)
            # Check large raster regions too: a page may contain only a digital header
            # while the eligibility/exclusion body is scanned.
            area = max(1, page.rect.get_area())
            large_image = any(info['bbox'] and pymupdf.Rect(info['bbox']).get_area()/area > 0.15
                              for info in page.get_image_info())
            garbled = text.count('\ufffd') > max(2, len(text)*0.02)
            if len(normalized(text)) < 20 or large_image or garbled:
                pending.append(number)
            pages[number] = text
        return pages, pending


def render_page(data, number):
    import pymupdf
    with pymupdf.open(stream=data, filetype='pdf') as document:
        page = document[number-1]
        scale = min(2.5, 3000 / max(page.rect.width, page.rect.height))
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes('png')


def complete_ocr(data, pages, pending, recognize, warnings=None):
    """페이지 번호를 보존한다. 성공한 페이지는 메모리에 남겨 재호출을 방지한다."""
    if warnings is None:
        warnings = []
    for number in list(pending):
        result = recognize(render_page(data, number), number)
        if result.is_blank:
            if normalized(pages[number]):
                raise ValueError(f'p.{number}: 추출 텍스트와 이미지 판독이 다릅니다. 원본을 확인해 주세요.')
            pages[number] = ''
        else:
            pages[number] = result.text
            warnings.append(f'p.{number}: 이미지 문자 인식 결과입니다. 숫자·조건은 원본과 대조해 주세요.')
            warnings.extend(f'p.{number}: {item}' for item in result.uncertainties)
        pending.remove(number)
    if not any(normalized(text) for text in pages.values()):
        raise ValueError('PDF에서 문자를 확인하지 못했습니다. 빈 문서이거나 판독하기 어려운 스캔입니다.')
    return warnings


def pdf_pages(data, recognize=None):
    pages, pending = inspect_pdf(data)
    if pending and recognize:
        return pages, complete_ocr(data, pages, pending, recognize)
    return pages, [f'p.{number}: 분석 시 이미지 문자 인식이 필요합니다.' for number in pending]

def load_documents(path: Path):
    if path.suffix.lower() == '.pdf':
        if path.stat().st_size > 30 * 1024**2:
            raise ValueError('PDF는 30MB 이하만 지원한다')
        return [(path.name, path.read_bytes())]
    if path.suffix.lower() != '.zip':
        raise ValueError('PDF 또는 ZIP을 입력해야 한다')
    with zipfile.ZipFile(path) as archive:
        entries = [f for f in archive.infolist() if not f.is_dir()
                   and f.filename.lower().endswith('.pdf')
                   and not f.filename.startswith('__MACOSX/')]
        if not entries or len(entries) > 100:
            raise ValueError('ZIP 안에는 PDF가 1~100개 있어야 한다')
        if sum(f.file_size for f in entries) > 200 * 1024**2:
            raise ValueError('PDF 압축 해제 크기 합계는 200MB 이하만 지원한다')
        result = []
        for entry in entries:
            if entry.file_size > 30 * 1024**2:
                raise ValueError('개별 PDF는 30MB 이하만 지원한다')
            # Read in memory: never extract paths supplied by the archive.
            result.append((entry.filename, archive.read(entry)))
        return result

def chunks(pages: dict[int, str], limit: int = 12000):
    """Split long pages too; no silent truncation of PDF text."""
    for number, text in pages.items():
        for start in range(0, len(text), limit - 300):
            yield {'page': number, 'text': text[start:start + limit]}
