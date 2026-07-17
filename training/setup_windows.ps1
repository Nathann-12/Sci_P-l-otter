param(
    [string]$Python = ".venv/Scripts/python.exe",
    [string]$EnvPath = "training/.venv"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $EnvPath)) {
    & $Python -m venv $EnvPath
}
$TrainingPython = Join-Path $EnvPath "Scripts/python.exe"
& $TrainingPython -m pip install --upgrade pip
# CUDA 12.8 is compatible with the RTX 3050 and the installed NVIDIA driver.
& $TrainingPython -m pip install torch --index-url https://download.pytorch.org/whl/cu128
& $TrainingPython -m pip install -r training/requirements.txt
& $TrainingPython training/preflight.py
