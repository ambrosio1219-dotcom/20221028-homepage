@echo off
chcp 65001 > nul
rem 기타 전시관 실행용 파일. 더블클릭하면 서버가 켜진다.
cd /d "%~dp0"
echo [1/2] Flask 설치 확인...
python -m pip install -q flask
echo [2/2] 서버 시작 - 브라우저에서 http://127.0.0.1:5000 으로 접속하세요.
echo       끄려면 이 창에서 Ctrl+C 를 누르세요.
echo.
python app.py
pause
