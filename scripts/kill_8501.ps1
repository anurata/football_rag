$conns = Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue
if ($conns) {
    foreach ($c in $conns) {
        $p = $c.OwningProcess
        if ($p -and $p -gt 0) {
            Write-Host "Killing PID $p"
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
}
Start-Sleep -Seconds 1
