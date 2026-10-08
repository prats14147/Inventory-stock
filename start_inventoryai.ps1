param(
    [int]$DatabaseWaitSeconds = 60,
    [int]$ApiWaitSeconds = 45
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendDir = Join-Path $projectRoot 'frontend'
$runtimeDir = Join-Path $projectRoot '.runtime'
$apiLog = Join-Path $runtimeDir 'api.log'
$apiErrorLog = Join-Path $runtimeDir 'api-error.log'
$webLog = Join-Path $runtimeDir 'web.log'
$webErrorLog = Join-Path $runtimeDir 'web-error.log'
$apiPidFile = Join-Path $runtimeDir 'api.pid'
$webPidFile = Join-Path $runtimeDir 'web.pid'
$apiUrl = 'http://127.0.0.1:8000/api/health'
$webUrl = 'http://127.0.0.1:5173'

function Test-TcpPort([string]$HostName, [int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        return $task.Wait(1000) -and $client.Connected
    } catch { return $false }
    finally { $client.Dispose() }
}

function Test-HttpReady([string]$Url) {
    try {
        $null = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
        return $true
    } catch { return $false }
}

function Wait-ForPort([string]$HostName, [int]$Port, [int]$Seconds, [string]$Name) {
    $until = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $until) {
        if (Test-TcpPort $HostName $Port) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Get-DatabaseUrl {
    # Match Pydantic Settings precedence: an inherited process environment
    # variable wins over the root .env file.
    if (-not [string]::IsNullOrWhiteSpace($env:DATABASE_URL)) {
        return $env:DATABASE_URL.Trim().Trim('"').Trim("'")
    }

    $envFile = Join-Path $projectRoot '.env'
    $line = Get-Content $envFile | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
    if (-not $line) { return $null }
    return (($line -replace '^\s*DATABASE_URL\s*=\s*', '').Trim().Trim('"').Trim("'"))
}

if (-not (Test-Path $python)) {
    throw "Python environment is missing. From the project folder, create .venv and install requirements.txt first. See README.md -> Installation."
}
if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    throw "Frontend packages are missing. Open a terminal in frontend, run npm install, then rerun this script."
}
if (-not (Test-Path (Join-Path $projectRoot '.env'))) {
    throw "Project .env is missing. Copy .env.example to .env in the project folder, then rerun this script."
}

Write-Host 'InventoryAI startup' -ForegroundColor Cyan
$databaseUrl = Get-DatabaseUrl
if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
    throw 'DATABASE_URL is missing. Set it in the root .env file before starting InventoryAI.'
}
try {
    $databaseHost = ([System.Uri]::new($databaseUrl)).DnsSafeHost.ToLowerInvariant()
} catch {
    throw 'DATABASE_URL is not a valid PostgreSQL connection URL. Check the root .env file.'
}
$isLocalDatabase = $databaseHost -in @('localhost', '127.0.0.1', '::1') -or $databaseHost.StartsWith('127.')
if ($isLocalDatabase) {
    Write-Host '1/4 Checking local PostgreSQL...'
    if (-not (Test-TcpPort '127.0.0.1' 5432)) {
        $docker = Get-Command docker -ErrorAction SilentlyContinue
        if ($docker) {
            Write-Host 'PostgreSQL is not answering yet. Asking Docker Compose to start the database...'
            & $docker.Source compose up -d postgres
            if ($LASTEXITCODE -ne 0) {
                throw 'Docker could not start PostgreSQL. Open Docker Desktop, then run this script again.'
            }
        } else {
            throw 'PostgreSQL is not answering on port 5432, and Docker is not installed/on PATH. Start your local PostgreSQL service or install/start Docker Desktop, then retry.'
        }
    }
    if (-not (Wait-ForPort '127.0.0.1' 5432 $DatabaseWaitSeconds 'PostgreSQL')) {
        throw "PostgreSQL did not become ready within $DatabaseWaitSeconds seconds. Check Docker Desktop or your PostgreSQL service."
    }
    Write-Host '   Local PostgreSQL accepts connections.' -ForegroundColor Green
} else {
    Write-Host "1/4 Using remote PostgreSQL host: $databaseHost"
    Write-Host '   The database migration in the next step will check the connection.' -ForegroundColor Green
}

Write-Host '2/4 Updating the database schema...'
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migrations failed. Check the DATABASE_URL in the root .env and the error shown above.' }
} finally { Pop-Location }
Write-Host '   Database schema is up to date. Existing inventory data is preserved.' -ForegroundColor Green

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

Write-Host '3/4 Checking the API...'
if (-not (Test-HttpReady $apiUrl)) {
    if (Test-TcpPort '127.0.0.1' 8000) {
        throw 'Port 8000 is occupied by a service that did not answer the InventoryAI health check. Close that service and retry.'
    }
    $apiProcess = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--reload','--host','127.0.0.1','--port','8000') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput $apiLog -RedirectStandardError $apiErrorLog -PassThru
    Set-Content -Path $apiPidFile -Value $apiProcess.Id
    $deadline = (Get-Date).AddSeconds($ApiWaitSeconds)
    while ((Get-Date) -lt $deadline -and -not (Test-HttpReady $apiUrl)) { Start-Sleep -Seconds 2 }
    if (-not (Test-HttpReady $apiUrl)) {
        $details = if (Test-Path $apiLog) { Get-Content $apiLog -Tail 12 | Out-String } else { 'No API log was created.' }
        throw "The API did not become ready. Recent API log: $apiLog`n$details"
    }
} else { Write-Host '   An InventoryAI API is already running; reusing it.' }
Write-Host "   API is ready: $apiUrl" -ForegroundColor Green

Write-Host '4/4 Checking the website...'
if (-not (Test-HttpReady $webUrl)) {
    if (Test-TcpPort '127.0.0.1' 5173) {
        throw 'Port 5173 is occupied by a service that did not answer as the website. Close that service and retry.'
    }
    $env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { throw 'npm.cmd was not found. Install Node.js, open a new terminal, and retry.' }
    $webProcess = Start-Process -FilePath $npm.Source -ArgumentList @('run','dev','--','--host','127.0.0.1') -WorkingDirectory $frontendDir -WindowStyle Hidden -RedirectStandardOutput $webLog -RedirectStandardError $webErrorLog -PassThru
    Set-Content -Path $webPidFile -Value $webProcess.Id
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline -and -not (Test-HttpReady $webUrl)) { Start-Sleep -Seconds 2 }
    if (-not (Test-HttpReady $webUrl)) {
        $details = if (Test-Path $webLog) { Get-Content $webLog -Tail 12 | Out-String } else { 'No website log was created.' }
        throw "The website did not become ready. Recent website log: $webLog`n$details"
    }
} else { Write-Host '   A website is already running on port 5173; reusing it.' }

Write-Host ''
Write-Host 'InventoryAI is ready: http://127.0.0.1:5173' -ForegroundColor Green
Write-Host 'API health: http://127.0.0.1:8000/api/health'
Write-Host "Logs: $runtimeDir"
Write-Host 'To stop services started by this script, run .\stop_inventoryai.ps1'
