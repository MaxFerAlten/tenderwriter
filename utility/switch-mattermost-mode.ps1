[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("team", "enterprise")]
    [string]$Mode,

    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Path $PSScriptRoot -Parent
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "File .env non trovato in $repoRoot"
}

$backupPath = "$envPath.bak"
Copy-Item -LiteralPath $envPath -Destination $backupPath -Force

$targetValues = if ($Mode -eq "team") {
    @{
        MM_EDITION = "team"
        MM_OIDC_ENABLE = "false"
        TW_OIDC_ENABLE = "true"
        MM_LOGIN_REDIRECT_MODE = "plugin"
    }
} else {
    @{
        MM_EDITION = "enterprise"
        MM_OIDC_ENABLE = "true"
        TW_OIDC_ENABLE = "false"
        MM_LOGIN_REDIRECT_MODE = "off"
    }
}

$lines = Get-Content -LiteralPath $envPath

foreach ($key in $targetValues.Keys) {
    $pattern = '^{0}=' -f [regex]::Escape($key)
    $replacement = "{0}={1}" -f $key, $targetValues[$key]
    $found = $false

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = $replacement
            $found = $true
            break
        }
    }

    if (-not $found) {
        $lines += $replacement
    }
}

Set-Content -LiteralPath $envPath -Value $lines -Encoding ascii

Write-Host "Mattermost mode impostato su '$Mode' in $envPath" -ForegroundColor Green
Write-Host "Backup creato: $backupPath" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Valori attivi:" -ForegroundColor Cyan
foreach ($key in "MM_EDITION", "MM_OIDC_ENABLE", "TW_OIDC_ENABLE", "MM_LOGIN_REDIRECT_MODE") {
    Write-Host ("- {0}={1}" -f $key, $targetValues[$key])
}

if ($NoRestart) {
    Write-Host ""
    Write-Host "Nessun restart eseguito. Per applicare la modifica:" -ForegroundColor Yellow
    Write-Host "docker compose --profile keycloak --profile videochat up -d --force-recreate backend frontend mattermost mm-plugin-oidc"
    exit 0
}

Write-Host ""
Write-Host "Riavvio dei servizi interessati..." -ForegroundColor Cyan
Push-Location $repoRoot
try {
    docker compose --profile keycloak --profile videochat up -d --force-recreate backend frontend mattermost mm-plugin-oidc
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Switch completato." -ForegroundColor Green
