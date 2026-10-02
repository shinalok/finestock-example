# finestock-example

PyPI의 [finestock](https://pypi.org/project/finestock/) 라이브러리를 설치해서 사용하는 OAuth 예제입니다.

## 설치 및 실행

### 방법 1. pip + requirements.txt

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt     # finestock, python-dotenv 설치

copy .env.example .env              # 사용할 Provider의 APP_KEY / APP_SECRET 입력
python example_oauth.py
```

### 방법 2. uv

`pyproject.toml`이 있어 [uv](https://docs.astral.sh/uv/)로도 바로 실행할 수 있습니다.

```powershell
copy .env.example .env
uv run example_oauth.py
```

## 사용법

1. 증권사를 선택합니다. (한국투자증권 KIS, LS증권 LS, 키움증권 KIWOOM, DB증권 DB, NH투자증권 NH)
2. 모드(실전/모의투자)를 선택합니다. 내부적으로 `finestock.create_api(provider, mode=...)`를 사용합니다.
3. 메뉴에서 작업을 고릅니다.

| 메뉴 | 설명 |
| --- | --- |
| 1. OAuth 하기 | 접근 토큰을 발급받아 `.env`에 저장하고, 토큰 정보를 출력합니다. |
| 2. 저장된 토큰 확인 | `.env`에 저장된 토큰이 JWT인지, 만료 시각(exp)과 남은 시간은 얼마인지 보여줍니다. |
| 3. 증권사/모드 변경 | 증권사와 모드를 다시 선택합니다. |
| 0. 종료 | 프로그램을 종료합니다. |

메뉴 위에는 현재 선택과 저장된 토큰의 유효 여부(`✓ 유효 · 21시간 35분 남음`)가 표시됩니다.

### .env 키 규칙

| 용도 | 실전 | 모의투자 |
| --- | --- | --- |
| 앱 키 / 시크릿 (직접 입력) | `KIS_APP_KEY`, `KIS_APP_SECRET` | `KISV_APP_KEY`, `KISV_APP_SECRET` |
| 접근 토큰 (자동 저장) | `KIS_ACCESS_TOKEN` | `KISV_ACCESS_TOKEN` |

다른 증권사는 `KIS` 자리에 `LS`, `KIWOOM`, `DB`, `NH`를 넣으면 됩니다. 모의투자는 별도 키를 사용하며 실전 키로 대체하지 않습니다.
`.env`에는 실제 토큰이 저장되므로 커밋하지 마세요. (`.gitignore`에 등록되어 있습니다)

토큰 확인은 서버에 요청하지 않고 토큰 자체만 디코딩하므로, JWT가 아닌 토큰은 만료일을 알 수 없습니다.
