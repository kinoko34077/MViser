$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
. (Join-Path $repositoryRoot ".kinotch/scripts/path-containment.ps1")
$projectRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "project"))
$manifestPath = Assert-KntSafePath -Root $projectRoot -Candidate (Join-Path $projectRoot "public/manifest.webmanifest") -Description "PWA manifest"
$workerPath = Assert-KntSafePath -Root $projectRoot -Candidate (Join-Path $projectRoot "public/service-worker.js") -Description "PWA service worker"
$registrationPath = Assert-KntSafePath -Root $projectRoot -Candidate (Join-Path $projectRoot "src/pwa/register.js") -Description "PWA registration helper"
$errors = New-Object System.Collections.Generic.List[string]

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { [void]$errors.Add("missing public/manifest.webmanifest") }
else {
    try {
        $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace([string]$manifest.name)) { [void]$errors.Add("manifest.name is required") }
        if ([string]::IsNullOrWhiteSpace([string]$manifest.start_url)) { [void]$errors.Add("manifest.start_url is required") }
        elseif ([string]$manifest.start_url -match '^[\\/]|^[a-zA-Z][a-zA-Z0-9+.-]*:') { [void]$errors.Add("manifest.start_url must be relative to the Project base path") }
    }
    catch { [void]$errors.Add("manifest.webmanifest is not valid JSON") }
}
if (-not (Test-Path -LiteralPath $workerPath -PathType Leaf)) { [void]$errors.Add("missing public/service-worker.js") }
if (-not (Test-Path -LiteralPath $registrationPath -PathType Leaf)) { [void]$errors.Add("missing src/pwa/register.js") }

if ($errors.Count -gt 0) {
    foreach ($errorText in $errors) { Write-Error $errorText }
    exit 1
}
Write-Output "PWA Default: OK"
exit 0
