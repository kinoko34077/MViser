[CmdletBinding()]
param()

function New-AgentInvocationContext {
    param(
        [string]$RequestId = "",
        [string]$CorrelationId = "",
        $InputObject = $null,
        $Metadata = @{}
    )

    if ([string]::IsNullOrWhiteSpace($RequestId)) { $RequestId = [Guid]::NewGuid().ToString("N") }
    if ([string]::IsNullOrWhiteSpace($CorrelationId)) { $CorrelationId = [Guid]::NewGuid().ToString("N") }
    return [pscustomobject]@{
        requestId = $RequestId
        correlationId = $CorrelationId
        input = $InputObject
        metadata = $Metadata
    }
}

function New-AgentDiagnostic {
    param(
        [string]$Level = "info",
        [Parameter(Mandatory=$true)][string]$Message,
        $Data = @{}
    )

    return [pscustomobject]@{
        kind = "agent-diagnostic"
        level = $Level
        message = $Message
        data = $Data
    }
}

function New-AgentCapabilityReport {
    param(
        [string]$Version = "",
        [string[]]$Capabilities = @()
    )

    return [pscustomobject]@{
        version = $Version
        capabilities = @($Capabilities)
    }
}

function Invoke-AgentBoundaryHook {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)]$Value,
        [scriptblock]$Hook
    )

    if ($null -eq $Hook) { return $Value }
    $parameterCount = 0
    if ($Hook.Ast -and $Hook.Ast.ParamBlock) { $parameterCount = @($Hook.Ast.ParamBlock.Parameters).Count }
    if ($parameterCount -ge 2) { return (& $Hook $Value $Name) }
    return (& $Hook $Value)
}
