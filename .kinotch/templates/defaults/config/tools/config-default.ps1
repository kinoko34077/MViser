[CmdletBinding()]
param()

function ConvertTo-KntConfigProperties {
    param([AllowNull()]$Value)

    if ($null -eq $Value) { return @() }
    if ($Value -is [System.Collections.IDictionary]) {
        return @($Value.Keys | ForEach-Object {
            [pscustomobject]@{ Name = [string]$_; Value = $Value[$_] }
        })
    }
    return @($Value.PSObject.Properties | ForEach-Object {
        [pscustomobject]@{ Name = [string]$_.Name; Value = $_.Value }
    })
}

function Merge-KntConfigMaps {
    param([object[]]$Maps = @())

    $merged = [ordered]@{}
    foreach ($map in @($Maps)) {
        foreach ($property in @(ConvertTo-KntConfigProperties -Value $map)) {
            $merged[$property.Name] = $property.Value
        }
    }
    return [pscustomobject]$merged
}

function Protect-KntConfigForDisplay {
    param(
        [AllowNull()]$Config,
        [string[]]$SecretKeys = @(),
        [string]$RedactedValue = "[REDACTED]"
    )

    $protected = [ordered]@{}
    foreach ($property in @(ConvertTo-KntConfigProperties -Value $Config)) {
        if ($property.Name -in @($SecretKeys)) {
            $protected[$property.Name] = $RedactedValue
        }
        else {
            $protected[$property.Name] = $property.Value
        }
    }
    return [pscustomobject]$protected
}
