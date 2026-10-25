
$ErrorActionPreference = 'Stop'

# Always start from the PNIS project folder
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " PNIS AGRICULTURAL INTELLIGENCE DASHBOARD" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

# Confirm required files exist
if (-not (Test-Path ".\app.py")) {
    throw "app.py is missing from $PSScriptRoot"
}

if (-not (Test-Path ".\requirements.txt")) {
    throw "requirements.txt is missing from $PSScriptRoot"
}

# Install required packages
Write-Host "[1/3] Checking dashboard dependencies..." -ForegroundColor Cyan
python -m pip install -r .\requirements.txt

if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

# Validate Python syntax
Write-Host "[2/3] Validating dashboard code..." -ForegroundColor Cyan
python -m py_compile .\app.py

if ($LASTEXITCODE -ne 0) {
    throw "Python syntax validation failed."
}

# Launch the dashboard
Write-Host "[3/3] Starting PNIS..." -ForegroundColor Cyan
Write-Host "Open http://localhost:8501 in your browser." -ForegroundColor Yellow

python -m streamlit run .\app.py
