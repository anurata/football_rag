# scripts/restart_app.ps1
# Streamlitプロセスをプロセスツリーごと完全に強制終了し、クリーンに再起動するスクリプト

Write-Host "=== Streamlit クリーン再起動開始 ==="

# ポート8501をバインドしているプロセスを特定
$pids = Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique

if ($pids) {
    foreach ($pid_val in $pids) {
        if ($pid_val -gt 0) {
            Write-Host "ポート8501のプロセスツリーを強制終了中 (PID: $pid_val)..."
            taskkill /PID $pid_val /T /F 2>$null
            Stop-Process -Id $pid_val -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

# ポートが解放されるまで待機 (最大5秒)
$timeout = 5
while ($timeout -gt 0) {
    $active = Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue
    if (-not $active) { break }
    Start-Sleep -Milliseconds 500
    $timeout -= 0.5
}

Write-Host "ポート8501が解放されました。Streamlit を起動します..."
$env:PYTHONPATH = "."
python -m streamlit run app.py --server.port 8501 --server.headless true
