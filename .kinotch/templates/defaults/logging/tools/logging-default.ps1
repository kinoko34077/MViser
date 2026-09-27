[CmdletBinding()]
param()

function New-KntLogRecord {
    param(
        [string]$Level = "info",
        [Parameter(Mandatory=$true)][string]$Message,
        $Data = @{}
    )

    return [pscustomobject]@{
        timestamp = [DateTimeOffset]::UtcNow.ToString("o")
        level = $Level
        message = $Message
        data = $Data
    }
}

function Write-KntConsoleLog {
    param(
        [Parameter(Mandatory=$true)]$Record,
        [switch]$Json
    )

    $text = if ($Json) { ConvertTo-Json $Record -Depth 20 -Compress } else { "[$($Record.level)] $($Record.message)" }
    [Console]::Error.WriteLine($text)
}

function Invoke-KntLogSink {
    param(
        [Parameter(Mandatory=$true)]$Record,
        [scriptblock]$Sink,
        [scriptblock]$Redactor
    )

    $value = if ($null -ne $Redactor) { & $Redactor $Record } else { $Record }
    if ($null -ne $Sink) { [void](& $Sink $value) }
    return $value
}
