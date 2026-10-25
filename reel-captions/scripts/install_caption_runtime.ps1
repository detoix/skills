param(
  [Parameter(Mandatory = $true)]
  [string]$Python
)

if (!(Test-Path -LiteralPath $Python)) {
  throw "Python runtime not found: $Python"
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

& $Python -m pip install whisperx
if ($LASTEXITCODE -ne 0) { throw "whisperx install failed" }

& $Python (Join-Path $PSScriptRoot "check_caption_runtime.py")
if ($LASTEXITCODE -ne 0) { throw "Caption runtime check failed" }
