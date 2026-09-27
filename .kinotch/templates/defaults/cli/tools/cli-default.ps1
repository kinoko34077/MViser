[CmdletBinding()]
param()

function Get-CliCommonOptions {
    param([string[]]$Arguments = @())

    $remaining = New-Object System.Collections.Generic.List[string]
    $options = [ordered]@{
        Help = $false
        Version = $false
        Json = $false
        Quiet = $false
        Verbose = $false
        DryRun = $false
        Yes = $false
        RemainingArgs = @()
    }
    $afterTerminator = $false
    foreach ($argument in @($Arguments)) {
        if ($afterTerminator) {
            [void]$remaining.Add([string]$argument)
            continue
        }
        switch ([string]$argument) {
            "--" { $afterTerminator = $true; [void]$remaining.Add("--"); continue }
            "--help" { $options.Help = $true; continue }
            "--version" { $options.Version = $true; continue }
            "--json" { $options.Json = $true; continue }
            "--quiet" { $options.Quiet = $true; continue }
            "--verbose" { $options.Verbose = $true; continue }
            "--dry-run" { $options.DryRun = $true; continue }
            "--yes" { $options.Yes = $true; continue }
            default { [void]$remaining.Add([string]$argument) }
        }
    }
    $options.RemainingArgs = @($remaining.ToArray())
    return [pscustomobject]$options
}

function Write-CliOutput {
    param(
        [Parameter(Mandatory=$true)][AllowEmptyString()][string]$Message,
        [switch]$Quiet
    )

    if (-not $Quiet) {
        [Console]::Out.WriteLine($Message)
    }
}

function Write-CliDiagnostic {
    param(
        [Parameter(Mandatory=$true)][AllowEmptyString()][string]$Message,
        [switch]$VerboseOutput
    )

    if ($VerboseOutput) {
        [Console]::Error.WriteLine($Message)
    }
}

function Write-CliJson {
    param(
        [Parameter(Mandatory=$true)]$Value,
        [int]$Depth = 20
    )

    [Console]::Out.WriteLine((ConvertTo-Json $Value -Depth $Depth -Compress))
}

function Write-CliError {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [Parameter(Mandatory=$true)][string]$Message,
        [hashtable]$Details = @{}
    )

    $envelope = [ordered]@{
        error = $Code
        message = $Message
        details = $Details
    }
    [Console]::Error.WriteLine((ConvertTo-Json $envelope -Depth 20 -Compress))
}

function Write-CliResult {
    param(
        [Parameter(Mandatory=$true)]$Value,
        [switch]$Json
    )

    if ($Json) {
        Write-CliJson -Value $Value
        return
    }
    [Console]::Out.WriteLine([string]$Value)
}

function Exit-Cli {
    param([int]$Code = 0)
    exit $Code
}

function Show-CliHelp {
    param([string]$Usage = "Usage: <project command> [options]")
    [Console]::Out.WriteLine($Usage)
    [Console]::Out.WriteLine("  --help       Show help")
    [Console]::Out.WriteLine("  --version    Show version")
    [Console]::Out.WriteLine("  --json       Use machine-readable output")
    [Console]::Out.WriteLine("  --quiet      Reduce human-readable output")
    [Console]::Out.WriteLine("  --verbose    Enable diagnostic output")
    [Console]::Out.WriteLine("  --dry-run    Do not apply changes")
    [Console]::Out.WriteLine("  --yes        Confirm non-interactive operation")
}
