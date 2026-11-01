$ErrorActionPreference = "Stop"

$port = 8000
if ($env:PORT) {
    $parsedPort = 0
    if (-not [int]::TryParse($env:PORT, [ref]$parsedPort) -or $parsedPort -lt 1 -or $parsedPort -gt 65535) {
        throw "PORT must be a number between 1 and 65535."
    }
    $port = $parsedPort
}

$pythonCandidates = @()
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonCandidates += [pscustomobject]@{ Path = $venvPython; Prefix = @() }
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $pythonCandidates += [pscustomobject]@{ Path = $pythonCommand.Source; Prefix = @() }
}

$launcherCommand = Get-Command py -ErrorAction SilentlyContinue
if ($launcherCommand) {
    $pythonCandidates += [pscustomobject]@{ Path = $launcherCommand.Source; Prefix = @("-3") }
}

$python = $null
foreach ($candidate in $pythonCandidates) {
    & $candidate.Path @($candidate.Prefix) -c "import uvicorn" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    throw "Python with Uvicorn was not found. Install the app dependencies with: python -m pip install -r AI-Runtime/requirements.txt"
}

Write-Host "Starting Ardvark preview at http://localhost:$port"
Write-Host "Press Ctrl+C to stop the server."
Push-Location $PSScriptRoot
try {
    & $python.Path @($python.Prefix) -m uvicorn app:app --reload --host 0.0.0.0 --port $port
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
