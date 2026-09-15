$ErrorActionPreference = "Stop"

Write-Host "SmartStructureBot Kiro packaging" -ForegroundColor Cyan

$project = (Get-Location).Path
$outDir = Join-Path $env:USERPROFILE "Desktop\SmartStructureBot_Kiro_Handoff"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

Write-Host "Recording repository identity..."
git status | Out-File -Encoding utf8 (Join-Path $outDir "GIT_STATUS.txt")
git branch --show-current | Out-File -Encoding utf8 (Join-Path $outDir "GIT_BRANCH.txt")
git rev-parse HEAD | Out-File -Encoding utf8 (Join-Path $outDir "GIT_COMMIT.txt")
git log -1 --oneline | Out-File -Encoding utf8 (Join-Path $outDir "GIT_LAST_COMMIT.txt")
python --version 2>&1 | Out-File -Encoding utf8 (Join-Path $outDir "PYTHON_VERSION.txt")
git diff | Out-File -Encoding utf8 (Join-Path $outDir "UNCOMMITTED_CHANGES.patch")

Write-Host "Running baseline tests..."
python -m pytest -q tests *> (Join-Path $outDir "BASELINE_TESTS.txt")

Write-Host "Creating source snapshot..."
$zip = Join-Path $outDir "SmartStructureBot_SOURCE.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

tar.exe -a -c -f $zip `
  --exclude=.git `
  --exclude=.venv `
  --exclude=venv `
  --exclude=__pycache__ `
  --exclude=.pytest_cache `
  --exclude=research_runs `
  .

Write-Host "Searching common data folders..."
$manifest = Join-Path $outDir "DATA_MANIFEST_SHA256.txt"
"SMARTSTRUCTUREBOT DATA MANIFEST" | Out-File -Encoding utf8 $manifest
foreach ($folder in @("research_data", "simulator_data", "test_data")) {
    $p = Join-Path $project $folder
    if (Test-Path $p) {
        Get-ChildItem -Path $p -File -Recurse | ForEach-Object {
            $hash = Get-FileHash -Algorithm SHA256 $_.FullName
            "$($hash.Hash)  $($_.FullName.Substring($project.Length + 1))" | Add-Content -Encoding utf8 $manifest
        }
    }
}

Write-Host "Done." -ForegroundColor Green
Write-Host "Handoff folder: $outDir"
Write-Host "Add these documents to this folder before giving it to Kiro:"
Write-Host "  STRATEGY_MASTER_CONTRACT_TP1_ONLY.md"
Write-Host "  KIRO_MASS_TEST_HANDOFF.md"
Write-Host "  KIRO_RETURN_CHECKLIST.md"
Write-Host "  HANDOFF_UPLOAD_ORDER.md"
