[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [Parameter(Mandatory = $true)]
    [string]$PythonPath,

    [ValidateRange(5, 1440)]
    [int]$IntervalMinutes = 15,

    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$TaskName = 'MalakVaultSyncAgent'
)

$ErrorActionPreference = 'Stop'

$resolvedProject = (Resolve-Path -LiteralPath $ProjectPath).Path
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI (gh) no está instalado o no está en PATH.'
}

& gh auth status
if ($LASTEXITCODE -ne 0) {
    throw 'GitHub CLI no está autenticado.'
}

& $resolvedPython -m malak_vault_sync.cli validate-config `
    --config $resolvedConfig
if ($LASTEXITCODE -ne 0) {
    throw 'La configuración del agente no es válida.'
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "La tarea '$TaskName' ya existe. No se reemplazará automáticamente."
}

$arguments = (
    '-m malak_vault_sync.cli run-once --config "{0}"' -f $resolvedConfig
)
$action = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument $arguments `
    -WorkingDirectory $resolvedProject
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description 'Detecta cambios de Malak y prepara PR draft del Vault.'

Write-Host "Tarea '$TaskName' instalada correctamente."
