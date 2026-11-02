"""PC에서 학습한 조항 분류 모델. GPT 모델의 가중치를 수정하지 않는다."""
from pathlib import Path
from settings import ROOT

MODEL_PATH = ROOT / 'models' / 'clause_classifier.joblib'


def load_model(path=MODEL_PATH):
    if not path.is_file():
        return None
    import joblib
    return joblib.load(path)


def predict_hints(text, artifact, max_items=15):
    if artifact is None:
        return []
    lines = [line.strip() for line in text.splitlines() if len(line.strip())>=8]
    if not lines:
        return []
    model = artifact['pipeline']
    probabilities = model.predict_proba(lines)
    candidates=[]
    for line, values in zip(lines, probabilities):
        index=int(values.argmax())
        score=float(values[index])
        if score>=0.35:
            candidates.append({'text':line,'predicted_category':str(model.classes_[index]),
                               'score':round(score,4)})
    return sorted(candidates,key=lambda item:item['score'],reverse=True)[:max_items]
