"""종목코드를 입력해 현재가를 조회하는 프롬프트형 예제. (finestock 2.1 이상)

사전 준비:
    pip install -r requirements.txt
    .env에 사용할 Provider의 APP_KEY/APP_SECRET 입력 (example_oauth.py와 같은 .env를 사용)

.env에 저장된 [Provider]_ACCESS_TOKEN이 유효하면 재사용하고, 없거나 만료되었으면
OAuth로 새로 발급받아 저장한다. (매번 발급받으면 브로커의 토큰 발급 제한에 걸리기 쉽다.)
"""
import contextlib
import io
import sys
from loguru import logger
import finestock
from example_oauth import (
    ask, choose_provider_and_mode, label, load_credentials, oauth, pad, saved_expiry, saved_token,
    section, title, token_status)

SAMPLE_CODE = '005930'  # 삼성전자


def create_logged_in_api(provider, mode):
    """저장된 토큰을 재사용하거나 OAuth로 발급받아 조회 가능한 api를 돌려준다. 실패하면 None."""
    values = load_credentials(provider, mode)
    if values is None:
        return None
    _, token = saved_token(provider, mode)
    if token and token_status(token, saved_expiry(provider, mode))[0] != 'expired':
        print('  ✓ .env에 저장된 접근 토큰을 사용합니다.')
    else:
        if token:
            print('  ! 저장된 토큰이 만료되어 새로 발급받습니다.')
        result = oauth(provider, mode)
        if not result.ok:
            return None
        token = result.token
    api = finestock.create_api(provider, mode=mode)
    api.set_oauth_info(*values)
    api.set_access_token(token)
    return api


def number(value):
    """3,000 / 71,000.5 처럼 천 단위 구분자를 붙인다."""
    value = float(value)  # 일부 브로커는 숫자를 문자열로 돌려준다.
    return f'{value:,.0f}' if value.is_integer() else f'{value:,.2f}'


def date_text(workday):
    text = str(workday)
    return f'{text[:4]}-{text[4:6]}-{text[6:]}' if len(text) == 8 and text.isdigit() else text


def print_price(price, code):
    section(f'현재가 · {price.code or code}')
    rows = [
        ('기준일', date_text(price.workday) + (f' {price.time}' if price.time else '')),
        ('현재가', f'{number(price.price)}원'),
        ('시가', f'{number(price.open)}원'),
        ('고가', f'{number(price.high)}원'),
        ('저가', f'{number(price.low)}원'),
        ('거래량', f'{number(price.volume)}주'),
        ('거래대금', f'{number(price.volume_amt)}원'),
    ]
    for name, value in rows:
        print(f'  {pad(name, 9)}: {value}')


def fetch_price(api, code):
    """get_price를 호출해 (시세, 오류 로그)를 돌려준다. 네트워크/API 오류는 안내를 출력하고 시세를 None으로 돌려준다."""
    errors = []
    sink = logger.add(lambda message: errors.append(message.record['message']), level='ERROR')
    try:
        # 일부 브로커 구현이 디버그용 print를 남기므로 화면이 어지럽지 않게 가린다.
        with contextlib.redirect_stdout(io.StringIO()):
            return api.get_price(code), errors
    except finestock.FinestockNetworkError:
        print('  ✗ 네트워크 오류: 브로커 서버에 연결하지 못했습니다.')
    except finestock.FinestockAPIError as error:
        print(f'  ✗ API 오류 (status={error.status_code}): 브로커 서버 응답을 확인하세요.')
    finally:
        logger.remove(sink)
    return None, None


def token_may_be_expired(provider, mode):
    """저장된 토큰이 유효하다고 확인되지 않으면 만료를 의심한다. (JWT가 아닌 토큰은 만료를 알 수 없다.)"""
    _, token = saved_token(provider, mode)
    return not token or token_status(token, saved_expiry(provider, mode))[0] != 'valid'


def query_price(api, code, provider, mode):
    """현재가를 조회한다. 시세를 못 받고 토큰 만료가 의심되면 한 번 재발급해 다시 조회한다."""
    print('  … 조회하는 중입니다.')
    price, errors = fetch_price(api, code)
    if errors is None:
        return
    if price is None and token_may_be_expired(provider, mode):
        print('  ! 토큰이 만료되었을 수 있어 재발급 후 다시 조회합니다.')
        result = oauth(provider, mode)
        if result.ok:
            api.set_access_token(result.token)
            price, errors = fetch_price(api, code)
            if errors is None:
                return
    if price is None:
        print(f'  ✗ {code}의 시세를 가져오지 못했습니다.')
        for message in errors[-2:]:
            print(f'    - {message[:120]}')
        print('    종목코드, 장 운영 시간을 확인하세요. (메뉴 2번: 토큰 재발급)')
        return
    print_price(price, code)


def price_loop(api, provider, mode):
    """종목코드를 반복해서 입력받아 조회한다. 빈 입력이면 메뉴로 돌아간다."""
    section('현재가 조회')
    print(f'  종목코드 6자리를 입력하세요. (예: {SAMPLE_CODE} 삼성전자)\n  Enter만 누르면 메뉴로 돌아갑니다.')
    while True:
        code = ask('\n종목코드 > ').upper()
        if not code:
            return
        if len(code) != 6 or not code.isalnum():
            print('  ✗ 종목코드는 6자리 영문/숫자여야 합니다.')
            continue
        query_price(api, code, provider, mode)


def print_menu(provider, mode):
    title(label(provider, mode))
    _, token = saved_token(provider, mode)
    if token:
        state, text = token_status(token, saved_expiry(provider, mode))
        print(f'  저장된 토큰: {"✓" if state == "valid" else "!" if state == "unknown" else "✗"} {text}')
    else:
        print('  저장된 토큰: 없음')
    print('\n  1. 현재가 조회\n  2. 토큰 재발급 (OAuth)\n  3. 증권사/모드 변경\n  0. 종료')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    logger.remove()
    logger.add(sys.stdout, level='CRITICAL')
    title(f'finestock 현재가 예제  (v{getattr(finestock, "__version__", "?")})')
    provider, mode = choose_provider_and_mode()
    api = None  # 첫 조회 때 로그인하고, 증권사/모드를 바꾸면 다시 만든다.
    while provider is not None:
        print_menu(provider, mode)
        action = ask('\n번호 입력 > ')
        if action == '1':
            if api is None:
                section('로그인')
                api = create_logged_in_api(provider, mode)
            if api is not None:
                price_loop(api, provider, mode)
        elif action == '2':
            result = oauth(provider, mode)
            if result.ok and api is not None:
                api.set_access_token(result.token)
        elif action == '3':
            provider, mode = choose_provider_and_mode()
            api = None
        elif action == '0':
            break
        else:
            print('  ✗ 0, 1, 2, 3 중에서 선택하세요.')
    print('\n종료합니다.')


if __name__ == '__main__':
    main()
