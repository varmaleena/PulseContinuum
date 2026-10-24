$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$demoPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
& $demoPython -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
Push-Location frontend
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
$backend = Start-Process -FilePath $demoPython -ArgumentList '-m','uvicorn','main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory "$PSScriptRoot/backend" -WindowStyle Hidden -PassThru
$frontend = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','npm.cmd run start -- --port 3000' -WorkingDirectory "$PSScriptRoot/frontend" -WindowStyle Hidden -PassThru
try {
    Write-Host 'PulseContinuum: http://localhost:3000 | API: http://localhost:8000/docs'
    while (-not $backend.HasExited -and -not $frontend.HasExited) { Start-Sleep -Seconds 1 }
} finally {
    foreach ($demoProcess in @($backend, $frontend)) {
        if (-not $demoProcess.HasExited) { taskkill.exe /PID $demoProcess.Id /T /F | Out-Null }
    }
}
