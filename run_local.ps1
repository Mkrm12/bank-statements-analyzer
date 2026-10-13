# Pulse AI - Local Development Runner
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "🏦 Pulse AI: Local Development Server" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

# Set local development environment
$env:DEV_MODE = "true"

# Verify .venv
if (-not (Test-Path ".\.venv\Scripts\streamlit.exe")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

Write-Host "Starting Streamlit on http://localhost:8501 ..." -ForegroundColor Green
.\.venv\Scripts\streamlit.exe run app.py --server.port=8501 --server.address=localhost

