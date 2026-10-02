"""Provider·모드(실전/모의) 선택 → OAuth 실행. (finestock 2.1 이상)

사전 준비:
    pip install -r requirements.txt   # finestock(PyPI) + python-dotenv
    .env.example을 .env로 복사한 뒤 사용할 Provider의 APP_KEY/APP_SECRET 입력
"""
from pathlib import Path
import sys
from dotenv import dotenv_values
from loguru import logger
import finestock
from finestock import APIProvider

ENV_PATH = Path(__file__).resolve().with_name('.env')
# 2.1부터는 증권사 Provider + mode로 선택한다. LSV, KISV 등 V 접미사 Provider는 호환용이다.
# EBEST는 LS증권으로 이름이 변경되어 선택 대상에서 제외한다.
PROVIDERS = [p for p in APIProvider if p is not APIProvider.EBEST and not p.name.endswith('V')]


def select_provider():
    providers = PROVIDERS
    while True:
        print('\nProvider 선택 (이름 또는 번호, 0: 종료)')
        for number, provider in enumerate(providers, 1):
            print(f'{number}. {provider.name}')
        choice = input('Provider: ').strip().upper()
        if choice == '0':
            return None
        if choice in APIProvider.__members__ and APIProvider[choice] in providers:
            return APIProvider[choice]
        if choice.isdigit() and 1 <= int(choice) <= len(providers):
            return providers[int(choice) - 1]
        print('목록의 이름이나 번호를 입력하세요.')


def select_mode(provider):
    while True:
        choice = input('모드 (1. 실전, 2. 모의투자): ').strip()
        if choice in ('1', '2'):
            return 'live' if choice == '1' else 'virtual'
        print('1 또는 2를 입력하세요.')


def oauth(provider, mode):
    settings = dotenv_values(ENV_PATH, encoding='utf-8-sig', interpolate=False)
    # 모의투자는 별도 키를 사용한다. (.env의 LSV_APP_KEY 등)
    prefix = provider.name + ('V' if mode == 'virtual' else '')
    names = [f'{prefix}_APP_KEY', f'{prefix}_APP_SECRET']
    values = [(settings.get(name) or '').strip() for name in names]
    missing = [name for name, value in zip(names, values)
               if not value or value.upper().startswith('YOUR_')]
    if missing:
        print(f'설정이 필요합니다. {ENV_PATH}에 다음 항목을 입력하세요:')
        for name in missing:
            print(f'  {name}="발급받은 값"')
        return False
    api = finestock.create_api(provider, mode=mode)
    api.set_oauth_info(*values)
    try:
        api.oauth()
    except finestock.FinestockNetworkError:
        print('네트워크 오류: 브로커 서버에 연결하지 못했습니다.')
        return False
    except finestock.FinestockAPIError as error:
        print(f'API 오류: status={error.status_code}. 키와 브로커 설정을 확인하세요.')
        return False
    if not api.get_access_token():
        print('토큰 발급 실패: 앱 키와 시크릿, Provider 설정을 확인하세요.')
        return False
    print(f'{provider.name}({mode}) OAuth 성공: 접근 토큰이 발급되었습니다.')
    return True


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    logger.remove()
    logger.add(sys.stdout, level='CRITICAL')
    print(f'finestock {getattr(finestock, "__version__", "")}')
    provider = select_provider()
    mode = select_mode(provider) if provider else None
    while provider is not None:
        print(f'\n선택한 Provider: {provider.name} ({mode})')
        print('1. OAuth 하기\n2. Provider/모드 변경\n0. 종료')
        action = input('선택: ').strip()
        if action == '1':
            oauth(provider, mode)
        elif action == '2':
            provider = select_provider()
            mode = select_mode(provider) if provider else None
        elif action == '0':
            return
        else:
            print('0, 1, 2 중 선택하세요.')


if __name__ == '__main__':
    main()
