[CmdletBinding()]
param()

function New-ApiRequestContext {
    param(
        [string]$RequestId = "",
        [string]$CorrelationId = ""
    )

    if ([string]::IsNullOrWhiteSpace($RequestId)) {
        $RequestId = [Guid]::NewGuid().ToString("N")
    }
    if ([string]::IsNullOrWhiteSpace($CorrelationId)) {
        $CorrelationId = [Guid]::NewGuid().ToString("N")
    }
    return [pscustomobject]@{
        requestId = $RequestId
        correlationId = $CorrelationId
    }
}

function New-ApiHealthResponse {
    param(
        [string]$Name = "service",
        [string]$Version = ""
    )

    $response = [ordered]@{
        status = "ok"
        name = $Name
    }
    if (-not [string]::IsNullOrWhiteSpace($Version)) {
        $response.version = $Version
    }
    return [pscustomobject]$response
}

function New-ApiErrorEnvelope {
    param(
        [Parameter(Mandatory=$true)][string]$Code,
        [Parameter(Mandatory=$true)][string]$Message,
        [object]$Details,
        [string]$RequestId = ""
    )

    $envelope = [ordered]@{
        error = $Code
        message = $Message
    }
    if ($PSBoundParameters.ContainsKey("Details")) {
        $envelope.details = $Details
    }
    if (-not [string]::IsNullOrWhiteSpace($RequestId)) {
        $envelope.requestId = $RequestId
    }
    return [pscustomobject]$envelope
}

function Invoke-ApiHook {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)]$Value,
        [scriptblock]$Hook
    )

    if ($null -eq $Hook) { return $Value }
    $parameterCount = 0
    if ($Hook.Ast -and $Hook.Ast.ParamBlock) {
        $parameterCount = @($Hook.Ast.ParamBlock.Parameters).Count
    }
    if ($parameterCount -ge 2) {
        return (& $Hook $Value $Name)
    }
    return (& $Hook $Value)
}
