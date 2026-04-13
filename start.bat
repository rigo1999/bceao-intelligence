@echo off
echo Starting BCEAO RAG...

:: Backend
start "BCEAO API" cmd /k "cd /d %~dp0 && venv\Scripts\activate && uvicorn api:app --host 0.0.0.0 --port 8000 --reload"

:: Wait a moment then start frontend
timeout /t 2 /nobreak >nul

:: Frontend
start "BCEAO UI" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo  Backend  : http://localhost:8000
echo  Frontend : http://localhost:5173
echo.
