param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$dashboard = Join-Path $repoRoot 'services/dashboard'
$dist = Join-Path $dashboard 'web/dist'
$url = 'http://127.0.0.1:8090'
$configUrl = "$url/api/workspaces/config"

function Get-WorkbenchConfig {
    try {
        $response = Invoke-RestMethod -Uri $configUrl -TimeoutSec 2
        if ($null -ne $response.ai_available -and $null -ne $response.max_source_chars) {
            return $response
        }
    } catch {
        return $null
    }
    return $null
}

if (-not (Test-Path -LiteralPath $dist -PathType Container)) {
    throw "The dashboard frontend has not been built. Follow the setup steps in services/dashboard/README.md, then run Start-Workbench.ps1 again."
}

$pythonCandidates = @(
    (Join-Path $dashboard '.venv/Scripts/python.exe'),
    (Join-Path $repoRoot '.tools/workbench-venv/Scripts/python.exe')
)
$python = $null
foreach ($candidate in $pythonCandidates) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    try {
        & $candidate -c 'import fastapi, uvicorn, pnp_okf' *> $null
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    } catch {
        # Broken venvs can emit stderr as a PowerShell native-command error.
        # Treat them as unavailable and try the workspace-local fallback.
    }
}
if (-not $python) {
    throw "No ready dashboard Python environment was found. Follow the Python setup steps in services/dashboard/README.md, then run Start-Workbench.ps1 again."
}

$existing = Get-WorkbenchConfig
if (-not $existing) {
    $listener = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $listener.BeginConnect('127.0.0.1', 8090, $null, $null)
        if ($connect.AsyncWaitHandle.WaitOne(500)) {
            try { $listener.EndConnect($connect) } catch { }
            if ($listener.Connected) {
                throw 'Port 8090 is already in use by another application. Close that application and run Start-Workbench.ps1 again.'
            }
        }
    } finally {
        $listener.Dispose()
    }

    $process = Start-Process -FilePath $python -ArgumentList @('app.py') `
        -WorkingDirectory $dashboard -WindowStyle Hidden -PassThru
    $deadline = (Get-Date).AddSeconds(25)
    do {
        Start-Sleep -Milliseconds 400
        $existing = Get-WorkbenchConfig
        if ($process.HasExited -and -not $existing) {
            throw 'The workbench server stopped during startup. Check the Python setup and frontend build in services/dashboard/README.md.'
        }
    } while (-not $existing -and (Get-Date) -lt $deadline)

    if (-not $existing) {
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        throw 'The workbench did not become ready within 25 seconds. Check the setup steps in services/dashboard/README.md.'
    }
}

if (-not $NoBrowser) {
    Start-Process $url
}
Write-Host "Campaign workbench is ready at $url"
