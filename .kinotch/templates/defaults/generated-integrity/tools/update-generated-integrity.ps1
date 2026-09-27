param(
    [Parameter(Mandatory=$true)][string]$Artifact,
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Generator
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
. (Join-Path $repositoryRoot ".kinotch/scripts/path-containment.ps1")
$projectRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "project"))
$configPath = Assert-KntSafeWritePath -Root $projectRoot -Candidate (Join-Path $projectRoot "generated-integrity.json") -Description "generated-integrity configuration"
if ([IO.Path]::IsPathRooted($Artifact) -or [IO.Path]::IsPathRooted($Source)) {
    throw "Generated source and artifact paths must be relative to the Project root"
}
$artifactPath = Assert-KntSafePath -Root $projectRoot -Candidate (Join-Path $projectRoot $Artifact) -Description "Generated artifact path"
$sourcePath = Assert-KntSafePath -Root $projectRoot -Candidate (Join-Path $projectRoot $Source) -Description "Generated source path"
if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) { throw "Generated artifact not found: $Artifact" }
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw "Generated source not found: $Source" }
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw "generated-integrity.json is missing" }
$config = Get-Content -Raw -Encoding UTF8 $configPath | ConvertFrom-Json
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath).Hash.ToLowerInvariant()
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifactPath).Hash.ToLowerInvariant()
$entry = [pscustomobject]@{
    source = $Source
    source_sha256 = $sourceHash
    artifact = $Artifact
    sha256 = $hash
    generator = $Generator
}
$existing = @($config.entries | Where-Object { [string]$_.artifact -ne $Artifact })
$config.entries = @($existing + $entry)
[IO.File]::WriteAllText($configPath, (ConvertTo-Json $config -Depth 10) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "Updated generated-integrity entry: $Artifact"
