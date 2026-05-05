$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Split-Path -Parent $scriptDir
$venvDir = Join-Path $skillRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"
$requirementsFile = Join-Path $scriptDir "requirements-standalone.txt"
$wheelsDir = Join-Path $scriptDir "temp_wheels\wheels\Windows\Torch280"
$patchDir = Join-Path $scriptDir "trellis2_core\patch"

Write-Host "Setting up standalone TRELLIS.2 GGUF environment..." -ForegroundColor Cyan

$pythonVer = & python --version 2>&1
if ($pythonVer -notmatch "3\.12") {
    throw "Python 3.12 is required. Found: $pythonVer"
}

if (-not (Test-Path $venvDir)) {
    Write-Host "Creating virtual environment at $venvDir" -ForegroundColor Green
    & python -m venv $venvDir
}

& $venvPip install --upgrade pip

Write-Host "Installing PyTorch 2.8 CUDA 12.8 build..." -ForegroundColor Green
& $venvPip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "Installing Python dependencies..." -ForegroundColor Green
& $venvPip install -r $requirementsFile
& $venvPip install xformers

Write-Host "Installing local CUDA wheels..." -ForegroundColor Green
$wheelNames = @(
    "cumesh-1.0-cp312-cp312-win_amd64.whl",
    "nvdiffrast-0.4.0-cp312-cp312-win_amd64.whl",
    "nvdiffrec_render-0.0.0-cp312-cp312-win_amd64.whl",
    "flex_gemm-0.0.1-cp312-cp312-win_amd64.whl",
    "o_voxel-0.0.1-cp312-cp312-win_amd64.whl"
)

foreach ($wheelName in $wheelNames) {
    $wheelPath = Join-Path $wheelsDir $wheelName
    if (-not (Test-Path $wheelPath)) {
        throw "Required wheel not found: $wheelPath"
    }
    & $venvPip install $wheelPath
}

Write-Host "Applying local patches..." -ForegroundColor Green
$patchScript = @"
from pathlib import Path
import importlib.util
import shutil
import sys

patch_dir = Path(r"$patchDir")
mapping = {
    "remeshing.py": "cumesh",
    "flexible_dual_grid.py": "o_voxel",
}

for filename, module_name in mapping.items():
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise RuntimeError(f"Could not locate installed module: {module_name}")
    module_root = Path(spec.origin).resolve().parent
    src = patch_dir / filename
    dst = module_root / filename
    if not src.exists():
        raise RuntimeError(f"Patch file missing: {src}")
    shutil.copy2(src, dst)
    print(f"Patched {dst}")
"@

$patchScript | & $venvPython -

Write-Host "Environment ready." -ForegroundColor Cyan
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. .\.venv\Scripts\python.exe scripts\download_models.py" -ForegroundColor White
Write-Host "  2. .\.venv\Scripts\python.exe scripts\inference.py --input .\monster.jpg --output .\monster.glb --pipeline-type 512" -ForegroundColor White
