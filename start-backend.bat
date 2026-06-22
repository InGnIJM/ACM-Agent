@echo off
cd /d "%~dp0backend"

echo === ACM Agent Backend ===
echo.

echo [1/5] Freeing port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000.*LISTENING"') do (
    taskkill /F /PID %%a 2>nul
)
echo   Port 3000 cleared.

echo.
echo [2/5] Checking PostgreSQL...
node check-db.js
if %errorlevel% neq 0 (
    echo   PostgreSQL is not running. Please start it first.
    pause
    exit /b 1
)

echo.
echo [3/5] Checking Reranker...
set RERANK_GGUF=%~dp0ollama-models\qwen3-reranker\Qwen3-Reranker-0.6B.F16.gguf
set LLAMA_SERVER_CUDA=%~dp0ollama-models\llama-cpp\llama-server.exe
set LLAMA_SERVER_OLLAMA=%LOCALAPPDATA%\Programs\Ollama\lib\ollama\llama-server.exe
set RERANK_MODE=0
set LLAMA_SERVER=

if not exist "%RERANK_GGUF%" (
    echo   WARNING: Reranker GGUF not found.
    echo   Backend will fall back to rough scores for ranking.
    set RERANK_MODE=0
) else if exist "%LLAMA_SERVER_CUDA%" (
    echo   CUDA llama-server found - GPU mode.
    set LLAMA_SERVER=%LLAMA_SERVER_CUDA%
    set RERANK_MODE=1
) else if exist "%LLAMA_SERVER_OLLAMA%" (
    echo   Using Ollama bundled llama-server ^(CPU mode^).
    set LLAMA_SERVER=%LLAMA_SERVER_OLLAMA%
    set RERANK_MODE=1
) else (
    echo   WARNING: No llama-server found. Backend will use rough scores.
    set RERANK_MODE=0
)

echo.
echo [4/5] Starting Rerank service...
netstat -ano | findstr ":8088.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo   Rerank service already running on port 8088.
    goto :skip_rerank
)

if "%RERANK_MODE%"=="1" (
    start "RerankService" /MIN ^
      "%LLAMA_SERVER%" ^
      -m "%RERANK_GGUF%" --reranking --pooling rank ^
      --port 8088 --host 127.0.0.1 -c 4096 -ub 4096 --gpu-layers 999
    timeout /t 5 /nobreak >nul
    curl -s http://127.0.0.1:8088/health >nul 2>&1
    if %errorlevel% equ 0 (
        echo   Rerank service: http://127.0.0.1:8088
    ) else (
        echo   WARNING: Rerank service may not be ready yet
    )
) else (
    echo   Reranker skipped - using rough score fallback.
)

:skip_rerank

echo.
echo [5/5] Starting NestJS server on port 3000...
echo   API : http://localhost:3000
echo   Docs: http://localhost:3000/api/docs
echo.

if exist tsconfig.tsbuildinfo del tsconfig.tsbuildinfo
npm run start:dev
pause
