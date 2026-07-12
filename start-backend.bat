@echo off
cd /d "%~dp0backend"

echo === ACM Agent Backend ===
echo.

echo [1/6] Freeing ports...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000.*LISTENING"') do (
    taskkill /F /PID %%a 2>nul
)
echo   Port 3000 cleared.

echo.
echo [2/6] Checking PostgreSQL...
node check-db.js
if %errorlevel% neq 0 (
    echo   PostgreSQL is not running. Please start it first.
    pause
    exit /b 1
)

echo.
echo [3/6] Checking models...
set LLAMA_SERVER=%~dp0ollama-models\llama-cpp\llama-server.exe
set EMBED_GGUF=%~dp0ollama-models\qwen3-embedding\Qwen3-Embedding-0.6B.Q8_0.gguf
set RERANK_GGUF=%~dp0ollama-models\qwen3-reranker\Qwen3-Reranker-0.6B.Q8_0.gguf
set EMBED_READY=0
set RERANK_READY=0

if not exist "%LLAMA_SERVER%" (
    echo   ERROR: CUDA llama-server not found at ollama-models\llama-cpp\llama-server.exe
    echo   Download from: https://github.com/ggml-org/llama.cpp/releases/tag/b9745
    echo   Files: llama-b9745-bin-win-cuda-12.4-x64.zip + cudart-llama-bin-win-cuda-12.4-x64.zip
    echo   Extract both to: ollama-models\llama-cpp\
    echo   ALL GPU SERVICES DISABLED.
    goto :skip_services
) else (
    echo   CUDA llama-server found.
)

if not exist "%EMBED_GGUF%" (
    echo   WARNING: Embedding GGUF not found at ollama-models\qwen3-embedding\
) else (
    echo   Embedding model: Q8_0
    set EMBED_READY=1
)

if not exist "%RERANK_GGUF%" (
    echo   WARNING: Reranker GGUF not found at ollama-models\qwen3-reranker\
) else (
    echo   Reranker model: Q8_0
    set RERANK_READY=1
)

echo.
echo [4/6] Starting Embedding service (port 8089)...
netstat -ano | findstr ":8089.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo   Embedding service already running on port 8089.
) else if "%EMBED_READY%"=="1" (
    start "EmbedService" /MIN ^
      "%LLAMA_SERVER%" ^
      -m "%EMBED_GGUF%" --embeddings ^
      --port 8089 --host 127.0.0.1 -c 32768 -ub 32768 --gpu-layers 999
    timeout /t 3 /nobreak >nul
    curl -s http://127.0.0.1:8089/health >nul 2>&1
    if %errorlevel% equ 0 (
        echo   Embedding service: http://127.0.0.1:8089 (GPU)
    ) else (
        echo   ERROR: Embedding service failed to start.
    )
) else (
    echo   Embedding service skipped - model not found.
)

echo.
echo [5/6] Starting Rerank service (port 8088)...
netstat -ano | findstr ":8088.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo   Rerank service already running on port 8088.
) else if "%RERANK_READY%"=="1" (
    start "RerankService" /MIN ^
      "%LLAMA_SERVER%" ^
      -m "%RERANK_GGUF%" --reranking --pooling rank ^
      --port 8088 --host 127.0.0.1 -c 1024 -ub 1024 --gpu-layers 999
    timeout /t 3 /nobreak >nul
    curl -s http://127.0.0.1:8088/health >nul 2>&1
    if %errorlevel% equ 0 (
        echo   Rerank service: http://127.0.0.1:8088 (GPU)
    ) else (
        echo   ERROR: Rerank service failed to start.
    )
) else (
    echo   Reranker skipped - using rough score fallback.
)

:skip_services

echo.
echo [5.5/6] Starting Rerank watchdog...
start "RerankWatchdog" /MIN powershell -ExecutionPolicy Bypass -File "%~dp0ensure-rerank.ps1"
echo   Rerank watchdog started.

echo.
echo [6/6] Starting NestJS server on port 3000...
echo   API : http://localhost:3000
echo   Docs: http://localhost:3000/api/docs
echo.

if exist tsconfig.tsbuildinfo del tsconfig.tsbuildinfo
npm run start:dev
pause
