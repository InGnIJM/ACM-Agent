@echo off
cd /d "%~dp0backend"

echo === ACM Agent Backend ===
echo.

echo [1/3] Freeing port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000.*LISTENING"') do (
    taskkill /F /PID %%a 2>nul
)
echo   Port 3000 cleared.

echo.
echo [2/3] Checking PostgreSQL...
node check-db.js
if %errorlevel% neq 0 (
    echo   PostgreSQL is not running. Please start it first.
    pause
    exit /b 1
)

echo.
echo [3/3] Starting NestJS server on port 3000...
echo   API : http://localhost:3000
echo   Docs: http://localhost:3000/api/docs
echo.

if exist tsconfig.tsbuildinfo del tsconfig.tsbuildinfo
npm run start:dev
pause
