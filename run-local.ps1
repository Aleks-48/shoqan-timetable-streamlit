param(
    [string]$PythonPath = '',
    [int]$Port = 8501
)

$repoRoot = $PSScriptRoot
if (-not $PythonPath) {
    $localVenv = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localVenv) {
        $PythonPath = $localVenv
    } else {
        throw "Set -PythonPath to Python 3.12 with requirements.txt installed, or create .venv in $repoRoot."
    }
}
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python interpreter not found: $PythonPath"
}
if ($Port -lt 1024 -or $Port -gt 65535) {
    throw 'Port must be between 1024 and 65535.'
}

$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'
& $PythonPath -B -m streamlit run (Join-Path $repoRoot 'app.py') `
    --server.headless=true --server.address=127.0.0.1 --server.port=$Port
exit $LASTEXITCODE
