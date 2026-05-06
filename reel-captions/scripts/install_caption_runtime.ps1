param(
  [string]$Python = "$env:USERPROFILE\Downloads\speech-gen\venv\Scripts\python.exe"
)

if (!(Test-Path -LiteralPath $Python)) {
  throw "Python runtime not found: $Python"
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

& $Python -m pip install whisperx
if ($LASTEXITCODE -ne 0) { throw "whisperx install failed" }

& $Python "C:\Users\kdeptula\skills\reel-captions\scripts\check_caption_runtime.py"
