"""PDF 지식 색인과 벡터 검색. GPT 가중치를 학습하는 모듈은 아니다."""
import hashlib
import json
import math
import os
from pathlib import Path
from settings import ROOT

INDEX_PATH = ROOT / 'knowledge_base' / 'index.json'
EMBEDDING_MODEL = 'text-embedding-3-small'


def dataset_directory(value=None):
    if value:
        path = Path(value).expanduser()
        return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    candidates = [ROOT / name for name in ('dataset', 'datasets', '데이터셋')]
    existing = [p for p in candidates if p.is_dir() and any(f.is_file() and f.suffix.lower()=='.pdf' for f in p.rglob('*'))]
    if len(existing) > 1:
        raise ValueError('PDF 폴더가 여러 개입니다. --dataset 옵션으로 사용할 폴더를 지정해 주세요.')
    return existing[0] if existing else ROOT / 'dataset'


def load_index(path=INDEX_PATH):
    if not path.is_file():
        return None
    index = json.loads(path.read_text(encoding='utf-8'))
    if index.get('version') != 1:
        raise ValueError('색인 형식이 달라 다시 구축해야 합니다.')
    return index


def save_index(index, path=INDEX_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def text_chunks(pages, size=1200, overlap=200):
    records = []
    for number, text in pages.items():
        for start in range(0, len(text), size-overlap):
            piece = text[start:start+size]
            if piece.strip():
                records.append({'page': int(number), 'text': piece})
    return records


def embed(client, texts, model=EMBEDDING_MODEL):
    vectors, tokens = [], 0
    for offset in range(0, len(texts), 32):
        response = client.embeddings.create(model=model, input=texts[offset:offset+32])
        data = sorted(response.data, key=lambda item: item.index)
        if len(data) != len(texts[offset:offset+32]):
            raise ValueError('임베딩 결과 개수가 맞지 않습니다.')
        vectors.extend(item.embedding for item in data)
        if response.usage:
            tokens += response.usage.total_tokens
    return vectors, tokens


def cosine(left, right):
    if len(left) != len(right):
        raise ValueError('임베딩 차원이 다릅니다. 색인을 다시 구축해 주세요.')
    denominator = math.sqrt(sum(x*x for x in left)*sum(x*x for x in right))
    return sum(a*b for a,b in zip(left,right))/denominator if denominator else 0.0


def search(index, query, client, document_hash=None, top_k=5):
    docs = [d for d in index['documents'] if document_hash is None or d['sha256']==document_hash]
    if not docs:
        return [], 0
    query_vectors, tokens = embed(client, [query[:4000]], index['embedding_model'])
    matches = []
    for doc in docs:
        for record in doc['chunks']:
            matches.append({'source':doc['name'], 'document_hash':doc['sha256'],
                            'page':record['page'], 'text':record['text'],
                            'score':cosine(query_vectors[0], record['embedding'])})
    return sorted(matches, key=lambda item:item['score'], reverse=True)[:top_k], tokens


def build(dataset, system, path=INDEX_PATH, model=EMBEDDING_MODEL, force=False):
    from pdf_utils import pdf_pages
    files = sorted(p for p in dataset.rglob('*') if p.is_file() and p.suffix.lower()=='.pdf')
    if not files:
        raise ValueError('선택한 폴더에 PDF가 없습니다. --dataset으로 폴더를 지정해 주세요.')
    old = load_index(path) if path.exists() and not force else None
    cached = {d['sha256']:d for d in old['documents']} if old and old['embedding_model']==model else {}
    documents, failures, embedding_tokens = [], [], 0
    for number, pdf in enumerate(files, 1):
        name = pdf.relative_to(dataset).as_posix()
        system.progress(f'[{number}/{len(files)}] {name}')
        try:
            if pdf.stat().st_size > 30*1024**2:
                raise ValueError('개별 PDF는 30MB 이하여야 합니다.')
            data = pdf.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest in cached:
                documents.append({**cached[digest], 'name':name})
                continue
            pages, warnings = pdf_pages(data, system.ocr_page)
            records = text_chunks(pages)
            if not records:
                raise ValueError('추출된 문자가 없어 색인을 만들 수 없습니다.')
            vectors, tokens = embed(system.client, [r['text'] for r in records], model)
            embedding_tokens += tokens
            for record, vector in zip(records, vectors):
                record['embedding'] = vector
            document = {'name':name, 'sha256':digest, 'pages':pages,
                        'warnings':warnings, 'chunks':records}
            documents.append(document)
            cached[digest] = document
        except Exception as error:
            reason = str(error) if isinstance(error,ValueError) else type(error).__name__
            failures.append({'document':name,'error':reason})
    if not documents:
        # Leave a previous valid index intact on complete failure.
        raise ValueError('모든 PDF의 색인 구축이 실패했습니다: '+json.dumps(failures,ensure_ascii=False))
    index = {'version':1, 'embedding_model':model, 'documents':documents,
             'build_summary':{'files':len(files), 'indexed':len(documents), 'failed':failures,
                              'embedding_tokens':embedding_tokens, 'ocr_usage':system.usage}}
    save_index(index,path)
    return index
