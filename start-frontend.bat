@echo off
cd /d "%~dp0frontend"
echo Starting ACM Agent Frontend on http://localhost:5173
npx vite --host 0.0.0.0 --port 5173
pause
