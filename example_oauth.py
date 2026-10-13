"""Provider·모드(실전/모의) 선택 → OAuth 실행. (finestock 2.1 이상)

사전 준비:
    pip install -r requirements.txt   # finestock(PyPI) + python-dotenv
    .env.example을 .env로 복사한 뒤 사용할 Provider의 APP_KEY/APP_SECRET 입력
"""
import base64
import json
import unicodedata
from typing import Any, NamedTuple, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from dotenv import dotenv_values, set_key, unset_key
from loguru import logger
import finestock
from finestock import APIProvider

ENV_PATH = Path(__file__).resolve().with_name('.env')
# 2.1부터는 증권사 Provider + mode로 선택한다. (LSV, KISV 등 V 접미사 Provider는 호환용,
# EBEST는 LS증권으로 이름이 변경되어 목록에서 제외)
PROVIDERS = [APIProvider.KIS, APIProvider.LS, APIProvider.KIWOOM, APIProvider.DB, APIProvider.NH]
BROKER_NAMES = {
    APIProvider.KIS: '한국투자증권',
    APIProvider.LS: 'LS증권',
    APIProvider.KIWOOM: '키움증권',
    APIProvider.DB: 'DB증권',
    APIProvider.NH: 'NH투자증권',
}
MODE_NAMES = {'live': '실전', 'virtual': '모의투자'}
WIDTH = 52
KST = timezone(timedelta(hours=9))  # 키움 expires_dt는 한국 시간(YYYYMMDDHHMMSS)


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(char) in 'WF' else 1 for char in text)


def pad(text, width):
    """한글(전각)을 2칸으로 계산해 오른쪽을 공백으로 채운다."""
    return text + ' ' * max(width - display_width(text), 0)


def title(text):
    print(f'\n{"=" * WIDTH}\n  {text}\n{"=" * WIDTH}')


def section(text):
    print(f'\n── {text} ' + '─' * max(WIDTH - display_width(text) - 4, 4))


def ask(prompt):
    """입력을 받는다. Ctrl+C/Ctrl+Z(EOF)는 종료로 처리한다."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)


def label(provider, mode=None):
    text = f'{BROKER_NAMES[provider]} ({provider.name})'
    return f'{text} · {MODE_NAMES[mode]}' if mode else text


def select_provider():
    """Provider를 선택한다. 0을 입력하면 None(종료)."""
    providers = PROVIDERS
    section('증권사 선택')
    for number, provider in enumerate(providers, 1):
        print(f'  {number}. {pad(BROKER_NAMES[provider], 14)}({provider.name})')
    print('  0. 종료')
    while True:
        choice = ask('\n번호 또는 이름 입력 > ').upper()
        if choice == '0':
            return None
        if choice in APIProvider.__members__ and APIProvider[choice] in providers:
            return APIProvider[choice]
        if choice.isdigit() and 1 <= int(choice) <= len(providers):
            return providers[int(choice) - 1]
        print(f'  ✗ 0~{len(providers)} 사이의 번호나 목록의 이름을 입력하세요.')


def select_mode(provider):
    """모드를 선택한다. 0을 입력하면 None(증권사 다시 선택)."""
    section(f'{BROKER_NAMES[provider]} 모드 선택')
    print('  1. 실전\n  2. 모의투자\n  0. 뒤로')
    while True:
        choice = ask('\n번호 입력 > ')
        if choice == '0':
            return None
        if choice in ('1', '2'):
            return 'live' if choice == '1' else 'virtual'
        print('  ✗ 0, 1, 2 중에서 선택하세요.')


def key_prefix(provider, mode):
    # 모의투자는 별도 키를 사용한다. (.env의 LSV_APP_KEY, LSV_ACCESS_TOKEN 등)
    return provider.name + ('V' if mode == 'virtual' else '')


def load_credentials(provider, mode):
    """.env에서 앱 키/시크릿을 읽어 (키, 시크릿)을 돌려준다. 없으면 안내를 출력하고 None."""
    settings = dotenv_values(ENV_PATH, encoding='utf-8-sig', interpolate=False)
    prefix = key_prefix(provider, mode)
    names = [f'{prefix}_APP_KEY', f'{prefix}_APP_SECRET']
    values = [(settings.get(name) or '').strip() for name in names]
    missing = [name for name, value in zip(names, values)
               if not value or value.upper().startswith('YOUR_')]
    if missing:
        print(f'  ✗ 설정이 필요합니다. 아래 항목을 .env에 입력하세요.\n    ({ENV_PATH})')
        for name in missing:
            print(f'    {name}="발급받은 값"')
        return None
    return values


class OAuthResult(NamedTuple):
    """oauth()의 결과. 성공 여부는 ok로 확인하고, 실패하면 error_code/error_message를 본다."""
    token: Optional[str] = None
    error_code: Optional[str] = None     # 증권사 오류 코드. 네트워크 등 자체 오류는 NETWORK 같은 값
    error_message: Optional[str] = None  # 사람이 읽을 오류 메시지
    response: Any = None                 # api.oauth()가 돌려준 원본 응답 (디버깅용)

    @property
    def ok(self):
        return bool(self.token)


# 증권사마다 오류 응답의 필드 이름이 다르다. (KIS error_code/error_description,
# 키움 return_code/return_msg, LS·NH·DB rsp_cd/rsp_msg 등) 흔한 이름을 순서대로 찾는다.
ERROR_CODE_KEYS = ('error_code', 'rsp_cd', 'return_code', 'msg_cd', 'code', 'error')
ERROR_MESSAGE_KEYS = ('error_description', 'rsp_msg', 'return_msg', 'msg1', 'message', 'msg')


def extract_error(response):
    """OAuth 응답에서 (오류 코드, 오류 메시지)를 뽑는다. 찾지 못하면 None으로 채운다."""
    if not isinstance(response, dict):
        text = str(response).strip()
        return None, text[:200] or None
    code = next((str(response[key]) for key in ERROR_CODE_KEYS if response.get(key) not in (None, '')), None)
    message = next((str(response[key]) for key in ERROR_MESSAGE_KEYS if response.get(key)), None)
    if code is None and message is None and response:
        message = json.dumps(response, ensure_ascii=False)[:200]  # 알 수 없는 형식이면 원본 요약
    return code, message


def fail(code, message, response=None):
    print(f'  ✗ 토큰 발급 실패: {message}')
    if code:
        print(f'    오류 코드: {code}')
    return OAuthResult(None, code, message, response)


def oauth(provider, mode):
    """OAuth로 토큰을 발급받아 .env에 저장하고 OAuthResult를 돌려준다."""
    section('OAuth 실행')
    values = load_credentials(provider, mode)
    if values is None:
        return OAuthResult(error_code='NO_CREDENTIALS', error_message='.env에 앱 키/시크릿이 없습니다.')
    prefix = key_prefix(provider, mode)
    print('  … 접근 토큰을 요청하는 중입니다.')
    api = finestock.create_api(provider, mode=mode)
    api.set_oauth_info(*values)
    try:
        response = api.oauth()
    except finestock.FinestockNetworkError:
        return fail('NETWORK', '브로커 서버에 연결하지 못했습니다. 인터넷 연결을 확인하세요.')
    except finestock.FinestockAPIError as error:
        return fail(str(error.status_code), '브로커 서버가 JSON이 아닌 응답을 보냈습니다. 서버 점검이나 장애일 수 있습니다.')
    token = api.get_access_token()
    if not token:
        # 키/시크릿이 틀리면 예외 없이 증권사의 오류 응답이 반환된다.
        code, message = extract_error(response)
        result = fail(code, message or '증권사가 토큰을 주지 않았습니다.', response)
        print('    위 메시지를 확인하고, 앱 키/시크릿과 Provider/모드 설정도 점검하세요.')
        return result
    token_name = f'{prefix}_ACCESS_TOKEN'
    save_token(token_name, token)
    print('  ✓ OAuth 성공: 접근 토큰이 발급되었습니다.')
    print(f'  ✓ .env에 {token_name}으로 저장했습니다.')
    expiry = None
    # 키움 토큰은 JWT가 아니라 만료일을 알 수 없으므로 응답의 expires_dt를 따로 저장한다.
    expires_dt = response.get('expires_dt') if isinstance(response, dict) else None
    expiry_name = f'{prefix}_EXPIRES_DT'
    if parse_expires_dt(expires_dt) is not None:
        save_token(expiry_name, str(expires_dt))
        expiry = parse_expires_dt(expires_dt)
        print(f'  ✓ .env에 {expiry_name}도 저장했습니다.')
    else:
        clear_saved(expiry_name)  # 이전 토큰의 만료일이 남아 새 토큰을 잘못 판단하지 않게 한다.
    print_token_info(token, expiry)
    return OAuthResult(token, response=response)


def save_token(name, token):
    """발급받은 토큰을 .env에 NAME=값 형태로 저장한다. 기존 항목은 덮어쓴다."""
    with open(ENV_PATH, 'rb') as file:
        encoding = 'utf-8-sig' if file.read(3) == b'\xef\xbb\xbf' else 'utf-8'
    set_key(ENV_PATH, name, token, quote_mode='always', encoding=encoding)


def decode_jwt(token):
    """JWT의 header/payload를 (서명 검증 없이) 디코딩한다. JWT가 아니면 None."""
    parts = token.split('.')
    if len(parts) != 3:
        return None
    try:
        header, payload = (
            json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
            for part in parts[:2])
    except ValueError:  # base64/JSON 디코딩 실패
        return None
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return None
    return header, payload


def format_time(timestamp):
    time = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone()
    return time.strftime('%Y-%m-%d %H:%M:%S')


def format_remaining(seconds):
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = ([f'{days}일'] if days else []) + ([f'{hours}시간'] if hours or days else [])
    return ' '.join(parts + [f'{minutes}분'])


def parse_expires_dt(value):
    """'20261014184728'(KST) 형식의 expires_dt를 epoch 초로 바꾼다. 형식이 맞지 않으면 None."""
    text = str(value or '').strip()
    if len(text) != 14 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, '%Y%m%d%H%M%S').replace(tzinfo=KST).timestamp()
    except ValueError:
        return None


def clear_saved(name):
    """.env에서 항목을 지운다. 없으면 아무것도 하지 않는다."""
    if name in dotenv_values(ENV_PATH, encoding='utf-8-sig', interpolate=False):
        unset_key(ENV_PATH, name, encoding='utf-8-sig')


def saved_expiry(provider, mode):
    """.env에 저장된 [Provider]_EXPIRES_DT를 epoch 초로 돌려준다. 없으면 None."""
    settings = dotenv_values(ENV_PATH, encoding='utf-8-sig', interpolate=False)
    return parse_expires_dt(settings.get(f'{key_prefix(provider, mode)}_EXPIRES_DT'))


def token_status(token, expiry=None):
    """토큰의 상태 한 줄 요약(valid/expired/unknown, 설명)을 돌려준다.
    JWT가 아니면 expiry(.env에 저장해 둔 만료 시각, epoch 초)를 쓴다."""
    decoded = decode_jwt(token)
    exp = decoded[1].get('exp') if decoded else None
    if not isinstance(exp, (int, float)):
        exp = expiry
    if not isinstance(exp, (int, float)):
        return 'unknown', '만료일 확인 불가'
    remaining = exp - datetime.now(timezone.utc).timestamp()
    if remaining <= 0:
        return 'expired', '만료됨'
    return 'valid', f'유효 · {format_remaining(remaining)} 남음'


def print_token_info(token, expiry=None):
    """토큰 형식(JWT 여부)과 만료 정보를 출력한다. 서버에 요청하지 않고 토큰 자체(와 저장된 expiry)만 본다."""
    rows = [('토큰', f'{token[:8]}…{token[-4:]} ({len(token)}자)')]
    decoded = decode_jwt(token)
    if decoded is None:
        rows.append(('형식', 'JWT 아님 (불투명 토큰)'))
        if expiry is None:
            rows.append(('만료', '토큰에서 확인할 수 없습니다'))
        else:
            state, text = token_status(token, expiry)
            mark = '✓' if state == 'valid' else '✗'
            rows.append(('만료', f'{format_time(expiry)}  {mark} {text} (발급 응답의 expires_dt)'))
    else:
        header, payload = decoded
        rows.append(('형식', f'JWT (alg={header.get("alg")}, typ={header.get("typ")})'))
        for key, name in (('iss', '발급자'), ('sub', '대상')):
            if key in payload:
                rows.append((name, str(payload[key])))
        if isinstance(payload.get('iat'), (int, float)):
            rows.append(('발급', format_time(payload['iat'])))
        if isinstance(payload.get('exp'), (int, float)):
            state, text = token_status(token)
            mark = '✓' if state == 'valid' else '✗'
            rows.append(('만료', f'{format_time(payload["exp"])}  {mark} {text}'))
        else:
            rows.append(('만료', '토큰에 exp 정보가 없습니다'))
    section('토큰 정보')
    for name, value in rows:
        print(f'  {pad(name, 8)}: {value}')
    if token_status(token, expiry)[0] == 'expired':
        print('\n  ! 토큰이 만료되었습니다. 메뉴 1번으로 다시 OAuth 하세요.')


def saved_token(provider, mode):
    settings = dotenv_values(ENV_PATH, encoding='utf-8-sig', interpolate=False)
    name = f'{key_prefix(provider, mode)}_ACCESS_TOKEN'
    return name, (settings.get(name) or '').strip()


def check_saved_token(provider, mode):
    """.env에 저장된 [Provider]_ACCESS_TOKEN을 읽어 확인한다."""
    name, token = saved_token(provider, mode)
    if not token:
        print(f'\n  ✗ {name}이 .env에 없습니다. 메뉴 1번으로 먼저 OAuth 하세요.')
        return
    print_token_info(token, saved_expiry(provider, mode))


def print_menu(provider, mode):
    title(f'{label(provider, mode)}')
    _, token = saved_token(provider, mode)
    if token:
        state, text = token_status(token, saved_expiry(provider, mode))
        print(f'  저장된 토큰: {"✓" if state == "valid" else "!" if state == "unknown" else "✗"} {text}')
    else:
        print('  저장된 토큰: 없음')
    print('\n  1. OAuth 하기 (토큰 발급)\n  2. 저장된 토큰 확인\n  3. 증권사/모드 변경\n  0. 종료')


def choose_provider_and_mode():
    """증권사와 모드를 순서대로 고른다. 종료하면 (None, None)."""
    while True:
        provider = select_provider()
        if provider is None:
            return None, None
        mode = select_mode(provider)
        if mode is not None:
            return provider, mode


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    logger.remove()
    logger.add(sys.stdout, level='CRITICAL')
    title(f'finestock OAuth 예제  (v{getattr(finestock, "__version__", "?")})')
    provider, mode = choose_provider_and_mode()
    while provider is not None:
        print_menu(provider, mode)
        action = ask('\n번호 입력 > ')
        if action == '1':
            oauth(provider, mode)
        elif action == '2':
            check_saved_token(provider, mode)
        elif action == '3':
            provider, mode = choose_provider_and_mode()
        elif action == '0':
            break
        else:
            print('  ✗ 0, 1, 2, 3 중에서 선택하세요.')
    print('\n종료합니다.')


if __name__ == '__main__':
    main()
