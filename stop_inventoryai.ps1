$runtimeDir = Join-Path $PSScriptRoot '.runtime'
foreach ($service in @('web', 'api')) {
    $pidFile = Join-Path $runtimeDir "$service.pid"
    if (Test-Path $pidFile) {
        $processId = [int](Get-Content $pidFile -Raw)
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        $expectedProcess = if ($service -eq 'api') { 'uvicorn' } else { 'npm|vite' }
        if ($process -and $process.CommandLine -match $expectedProcess) {
            & taskkill.exe /PID $processId /T /F | Out-Null
            Write-Host "Stopped $service (process $processId)."
        } elseif ($process) {
            Write-Host "Skipped process $processId because it no longer looks like the InventoryAI $service."
        } else {
            Write-Host "The InventoryAI $service process is already stopped."
        }
        Remove-Item -LiteralPath $pidFile -Force
    }
}
Write-Host 'Stop script finished. PostgreSQL is left running so your database stays available.'
