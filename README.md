# finestock-example

PyPI의 [finestock](https://pypi.org/project/finestock/) 라이브러리를 설치해서 사용하는 OAuth 예제입니다.

## 실행 방법

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt     # pip install finestock python-dotenv

copy .env.example .env              # 사용할 Provider의 APP_KEY / APP_SECRET 입력
python example_oauth.py
```

Provider(LS, KIS, KIWOOM, NH, DB)와 모드(실전/모의투자, `finestock.create_api(provider, mode=...)`)를 선택한 뒤 `1. OAuth 하기`로 접근 토큰을 발급받습니다.
