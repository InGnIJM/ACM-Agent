# Rerank Service Watchdog
# Monitors port 8088 and restarts the rerank service if it goes down.
# Run: powershell -ExecutionPolicy Bypass -File ensure-rerank.ps1

$ErrorActionPreference = "SilentlyContinue"
$port = 8088
$llamaServer = Join-Path $PSScriptRoot "ollama-models\llama-cpp\llama-server.exe"
$rerankGguf = Join-Path $PSScriptRoot "ollama-models\qwen3-reranker\Qwen3-Reranker-0.6B.Q8_0.gguf"

function Test-Port {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

function Start-Rerank {
    if (-not (Test-Path $llamaServer)) { Write-Host "ERROR: llama-server not found"; return $false }
    if (-not (Test-Path $rerankGguf)) { Write-Host "ERROR: reranker model not found"; return $false }
    Write-Host "Starting rerank service on port $port..."
    Start-Process -FilePath $llamaServer -ArgumentList "-m `"$rerankGguf`" --reranking --pooling rank --port $port --host 127.0.0.1 -c 1024 -ub 1024 --gpu-layers 999" -WindowStyle Minimized
    Start-Sleep -Seconds 3
    if (Test-Port) {
        Write-Host "Rerank service started successfully."
        return $true
    } else {
        Write-Host "ERROR: Rerank service failed to start."
        return $false
    }
}

Write-Host "Rerank watchdog started. Monitoring port $port..."

# Initial check
if (-not (Test-Port)) {
    Start-Rerank
}

# Monitor loop
while ($true) {
    Start-Sleep -Seconds 10
    if (-not (Test-Port)) {
        Write-Host "$(Get-Date -Format 'HH:mm:ss') Rerank service DOWN. Restarting..."
        Start-Rerank
    }
}
