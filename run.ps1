$venvChainlit = Join-Path $PSScriptRoot ".venv\Scripts\chainlit.exe"
$userChainlit = "C:\Users\yucha\AppData\Roaming\Python\Python311\Scripts\chainlit.exe"

if (Test-Path $venvChainlit) {
    & $venvChainlit run app.py
} elseif (Test-Path $userChainlit) {
    & $userChainlit run app.py
} else {
    Write-Host "chainlit not found. Run: pip install chainlit openai httpx" -ForegroundColor Red
}
