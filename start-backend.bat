@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0backend"

echo ============================================
echo   ACM Agent Backend 服务启动检测
echo ============================================
echo.

:: ─── 1. PostgreSQL 服务 ──────────────────────────────────────────
echo [1/4] 检测 PostgreSQL 服务...
powershell -NoProfile -Command "if ((Get-Service -Name 'postgresql-x64-18' -ErrorAction SilentlyContinue).Status -ne 'Running') { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    echo   状态: 关闭 - 正在启动...
    powershell -NoProfile -Command "Start-Process -FilePath 'net' -ArgumentList 'start','postgresql-x64-18' -Verb RunAs -Wait" 2>nul
    timeout /t 3 /nobreak >nul
    powershell -NoProfile -Command "if ((Get-Service -Name 'postgresql-x64-18').Status -ne 'Running') { exit 1 }" >nul 2>&1
    if !errorlevel! neq 0 (
        echo   [错误] PostgreSQL 启动失败，请以管理员身份运行此脚本
        pause
        exit /b 1
    )
    echo   状态: 已启动 √
) else (
    echo   状态: 运行中 √
)

:: ─── 2. pgvector 扩展检测 ────────────────────────────────────────
echo [2/4] 检测 pgvector 扩展...
node -e "
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();
prisma.\$queryRawUnsafe(\"SELECT extname FROM pg_extension WHERE extname = 'vector'\")
  .then(r => { if(r.length===0) process.exit(2); prisma.\$disconnect(); })
  .catch(() => process.exit(1))
" 2>nul

if %errorlevel% equ 1 (
    echo   [错误] 无法连接数据库，请确认 PostgreSQL 运行正常
    pause
    exit /b 1
)
if %errorlevel% equ 2 (
    echo   状态: pgvector 扩展未安装 - 正在安装...
    node -e "
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();
prisma.\$executeRawUnsafe('CREATE EXTENSION IF NOT EXISTS vector')
  .then(() => { console.log('   pgvector 扩展已安装 √'); prisma.\$disconnect(); })
  .catch(e => { console.error('   [错误] 安装失败:', e.message); process.exit(1); })
    "
    if !errorlevel! neq 0 (
        pause
        exit /b 1
    )
) else (
    echo   状态: pgvector 已就绪 √
)

:: ─── 3. Ollama 服务 ──────────────────────────────────────────────
echo [3/4] 检测 Ollama 服务...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo   状态: 未运行 - 正在启动...
    start "" "ollama" serve
    :: 等待 Ollama 就绪
    for /l %%i in (1,1,30) do (
        timeout /t 2 /nobreak >nul
        curl -s http://localhost:11434/api/tags >nul 2>&1
        if !errorlevel! equ 0 goto :ollama_ready
        echo   等待 Ollama 启动... (%%i/30)
    )
    echo   [错误] Ollama 启动超时
    pause
    exit /b 1
    :ollama_ready
    echo   状态: 已启动 √
) else (
    echo   状态: 运行中 √
)

:: 检查 embedding 模型
echo   检测 embedding 模型...
curl -s http://localhost:11434/api/tags | findstr /i "qwen3-embedding" >nul 2>&1
if %errorlevel% neq 0 (
    echo   [警告] qwen3-embedding 模型未找到，正在拉取...
    ollama pull qwen3-embedding:0.6b
    if !errorlevel! neq 0 (
        echo   [错误] 模型拉取失败
        pause
        exit /b 1
    )
) else (
    echo   模型 qwen3-embedding:0.6b 已就绪 √
)

:: ─── 4. 启动后端 ─────────────────────────────────────────────────
echo [4/4] 启动 NestJS 后端 (端口 3000)...
echo.
echo ============================================
echo   所有服务已就绪，启动后端...
echo   API 地址: http://localhost:3000
echo   API 文档: http://localhost:3000/api/docs
echo ============================================
echo.

npm run start:dev
pause
