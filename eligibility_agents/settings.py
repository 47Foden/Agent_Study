"""서버 전용 설정. API 키를 브라우저 입력이나 결과 파일에 전달하지 않는다."""
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent
_MIGRATION_LOCK = threading.Lock()


def configured(value):
    if not value or not str(value).strip():
        return False
    return not any(word in str(value).lower() for word in
                   ('replace_with', '본인의', '본인_', '서비스접속용_', 'your_api', '여기에'))


def migrate_example(root=ROOT):
    """이전 버전 .env.example의 실제 키를 .env로 옮긴 뒤 예시 값을 비운다.

    실제 키가 이관되기 전에 원본을 지우지 않는다. 기존 .env의 다른 키는 덮어쓰지 않는다.
    파일/키 내용은 출력하지 않는다. 앱 시작 시 서버에서만 수행한다.
    """
    example, target = root / '.env.example', root / '.env'
    with _MIGRATION_LOCK:
        if not example.is_file():
            return
        legacy = dotenv_values(example, encoding='utf-8-sig', interpolate=False)
        key = legacy.get('OPENAI_API_KEY')
        if not configured(key):
            return
        current = dotenv_values(target, encoding='utf-8-sig', interpolate=False) if target.is_file() else {}
        old_key = current.get('OPENAI_API_KEY')
        if configured(old_key) and old_key != key:
            raise ValueError('로컬 설정 파일의 키가 서로 다릅니다. 운영자가 .env를 확인해야 합니다.')
        if not target.exists():
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
        for name in ('OPENAI_API_KEY', 'OPENAI_MODEL', 'APP_PASSWORD', 'DEBATE_ROUNDS'):
            value = legacy.get(name)
            if configured(value) and not configured(current.get(name)):
                set_key(target, name, value, quote_mode='always', encoding='utf-8')
        saved = dotenv_values(target, encoding='utf-8', interpolate=False)
        if saved.get('OPENAI_API_KEY') != key:
            raise ValueError('키 이전을 완료하지 못했습니다. 운영자가 .env를 확인해야 합니다.')
        # Keep non-secret settings/comments; remove the credential from its old location.
        set_key(example, 'OPENAI_API_KEY', '', quote_mode='always', encoding='utf-8-sig')
        if configured(legacy.get('APP_PASSWORD')):
            set_key(example, 'APP_PASSWORD', '', quote_mode='always', encoding='utf-8-sig')


@dataclass(frozen=True, repr=False)
class ServerConfig:
    api_key: str = ''
    model: str = 'gpt-4o-mini'
    password: str = ''
    rounds: int = 2
    parser_model: str = ''
    require_trained_model: bool = True


def load_server_config(secrets=None, root=ROOT):
    migrate_example(root)
    local = dotenv_values(root / '.env', encoding='utf-8-sig', interpolate=False)
    def get(name, default=''):
        value = (secrets or {}).get(name) or os.getenv(name) or local.get(name)
        return str(value).strip() if configured(value) else default
    try:
        rounds = int(get('DEBATE_ROUNDS', '2'))
    except ValueError:
        raise ValueError('서버 토론 횟수 설정을 확인해야 합니다.') from None
    if rounds not in (1, 2, 3):
        raise ValueError('서버 토론 횟수는 1~3이어야 합니다.')
    return ServerConfig(get('OPENAI_API_KEY'), get('OPENAI_MODEL', 'gpt-4o-mini'),
                        get('APP_PASSWORD'), rounds, get('OPENAI_PARSER_MODEL'),
                        get('REQUIRE_TRAINED_MODEL', 'true').lower() not in ('false','0','no'))
