$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
. (Join-Path $repositoryRoot ".kinotch/scripts/path-containment.ps1")
$projectRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "project"))
$configPath = Assert-KntSafePath -Root $projectRoot -Candidate (Join-Path $projectRoot "generated-integrity.json") -Description "generated-integrity configuration"
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    Write-Error "generated-integrity.json is missing"
    exit 1
}
$config = Get-Content -Raw -Encoding UTF8 $configPath | ConvertFrom-Json
if ([int]$config.schema_version -ne 1 -or [string]$config.algorithm -ne "SHA-256") {
    Write-Error "Unsupported generated-integrity configuration"
    exit 1
}

$failed = $false
foreach ($entry in @($config.entries)) {
    $sourceRelative = [string]$entry.source
    $artifactRelative = [string]$entry.artifact
    if ([IO.Path]::IsPathRooted($sourceRelative) -or [IO.Path]::IsPathRooted($artifactRelative)) {
        Write-Error "Generated paths must be relative to the Project root"
        $failed = $true
        continue
    }
    try {
        $source = Assert-KntSafePath -Root $projectRoot -Candidate (Join-Path $projectRoot $sourceRelative) -Description "Generated source path"
        $artifact = Assert-KntSafePath -Root $projectRoot -Candidate (Join-Path $projectRoot $artifactRelative) -Description "Generated artifact path"
    }
    catch {
        Write-Error $_.Exception.Message
        $failed = $true
        continue
    }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        Write-Error "Generated source is missing: $($entry.source)"
        $failed = $true
        continue
    }
    if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
        Write-Error "Generated artifact is missing: $($entry.artifact)"
        $failed = $true
        continue
    }
    if ([string]$entry.source_sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        Write-Error "Generated source hash is missing or invalid: $($entry.source)"
        $failed = $true
        continue
    }
    if ([string]$entry.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        Write-Error "Generated artifact hash is missing or invalid: $($entry.artifact)"
        $failed = $true
        continue
    }
    $sourceActual = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant()
    if ($sourceActual -ne ([string]$entry.source_sha256).ToLowerInvariant()) {
        Write-Error "Generated source is stale: $($entry.source)"
        $failed = $true
    }
    if ($actual -ne ([string]$entry.sha256).ToLowerInvariant()) {
        Write-Error "Generated artifact is stale: $($entry.artifact)"
        $failed = $true
    }
}

if ($failed) { exit 1 }
Write-Output "Generated integrity: OK ($(@($config.entries).Count) artifact(s))"
exit 0
