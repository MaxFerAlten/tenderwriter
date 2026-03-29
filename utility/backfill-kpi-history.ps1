<#
.SYNOPSIS
Backfilla la history KPI dei tender in batch tramite le API admin del backend.

.DESCRIPTION
Lo script esegue:
1. Login admin su /api/auth/login
2. Resync opzionale del portfolio KPI
3. Enumerazione automatica dei tender oppure uso di una lista esplicita di ID
4. Richiesta di history backfill per batch
5. Polling di /api/admin/kpi/tenders/{id}/analysis-jobs/latest fino a succeeded o failed

Se -Password non viene passato, lo script lo richiede in modo interattivo per evitare
di salvarlo nella history della shell.

.PARAMETER Email
Email dell'utente admin da usare per il login.

.PARAMETER Password
Password dell'utente admin. Se omesso, viene richiesta a runtime.

.PARAMETER BaseUrl
Base URL del backend. Default: http://localhost:8000

.PARAMETER TenderIds
Lista opzionale di tender ID da backfillare. Se omessa, lo script scorre tutto il portfolio accessibile.

.PARAMETER BatchSize
Numero di tender da avviare per batch. Default: 10

.PARAMETER PollSeconds
Intervallo di polling tra i check dello stato job. Default: 2

.PARAMETER JobTimeoutSeconds
Timeout massimo per tender prima di marcarlo come failed. Default: 300

.PARAMETER PageSize
Dimensione pagina per la discovery dei tender. Default: 100

.PARAMETER MaxTenders
Numero massimo di tender da processare in discovery automatica. 0 significa nessun limite. Default: 0

.PARAMETER SkipPortfolioResync
Salta il POST iniziale a /api/admin/kpi/portfolio/resync.

.PARAMETER ContinueOnError
Continua anche se un tender fallisce o una richiesta batch genera errore.

.EXAMPLE
.\utility\backfill-kpi-history.ps1 -Email admin@example.com

.EXAMPLE
.\utility\backfill-kpi-history.ps1 -Email admin@example.com -TenderIds 12,18,24 -SkipPortfolioResync

.EXAMPLE
.\utility\backfill-kpi-history.ps1 -Email admin@example.com -Password "secret" -BatchSize 5 -MaxTenders 20
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Email,

    [string]$Password,

    [string]$BaseUrl = "http://localhost:8000",

    [int[]]$TenderIds,

    [ValidateRange(1, 100)]
    [int]$BatchSize = 10,

    [ValidateRange(1, 60)]
    [int]$PollSeconds = 2,

    [ValidateRange(30, 3600)]
    [int]$JobTimeoutSeconds = 300,

    [ValidateRange(1, 100)]
    [int]$PageSize = 100,

    [ValidateRange(0, 100000)]
    [int]$MaxTenders = 0,

    [switch]$SkipPortfolioResync,

    [switch]$ContinueOnError
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host ""
    Write-Host ("=== {0} ===" -f $Message) -ForegroundColor Cyan
}

function Normalize-BaseUrl {
    param([Parameter(Mandatory = $true)][string]$Url)
    return $Url.TrimEnd("/")
}

function Get-ApiUrl {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($Path.StartsWith("http://", [System.StringComparison]::OrdinalIgnoreCase) -or
        $Path.StartsWith("https://", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $Path
    }

    if (-not $Path.StartsWith("/")) {
        $Path = "/" + $Path
    }

    return "{0}{1}" -f $script:NormalizedBaseUrl, $Path
}

function ConvertTo-PlainText {
    param([Parameter(Mandatory = $true)][Security.SecureString]$SecureString)

    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Resolve-Password {
    if ($Password) {
        return $Password
    }

    $securePassword = Read-Host -Prompt "Admin password" -AsSecureString
    return ConvertTo-PlainText -SecureString $securePassword
}

function Get-PropertyValue {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $InputObject) {
        return $null
    }

    try {
        $property = $InputObject.PSObject.Properties[$Name]
        if ($null -ne $property) {
            return $property.Value
        }
    } catch {
    }

    return $null
}

function Get-HttpErrorDetail {
    param([Parameter(Mandatory = $true)][System.Management.Automation.ErrorRecord]$ErrorRecord)

    $exception = $ErrorRecord.Exception
    if ($null -eq $exception) {
        return "Unknown HTTP error."
    }

    $responseValue = Get-PropertyValue -InputObject $exception -Name "Response"
    if ($null -ne $responseValue) {
        $contentValue = Get-PropertyValue -InputObject $responseValue -Name "Content"
        if ($null -ne $contentValue) {
            try {
                if ($contentValue -is [System.Net.Http.HttpContent]) {
                    $body = $contentValue.ReadAsStringAsync().GetAwaiter().GetResult()
                } else {
                    $body = [string]$contentValue
                }

                if ($body) {
                    return $body
                }
            } catch {
            }
        }

        if ($responseValue -is [System.Net.WebResponse]) {
            try {
                $stream = $responseValue.GetResponseStream()
                if ($null -ne $stream) {
                    $reader = [System.IO.StreamReader]::new($stream)
                    try {
                        $body = $reader.ReadToEnd()
                        if ($body) {
                            return $body
                        }
                    } finally {
                        $reader.Dispose()
                        $stream.Dispose()
                    }
                }
            } catch {
            }
        }

        $reasonPhrase = Get-PropertyValue -InputObject $responseValue -Name "ReasonPhrase"
        $statusCode = Get-PropertyValue -InputObject $responseValue -Name "StatusCode"
        if ($null -ne $reasonPhrase -or $null -ne $statusCode) {
            $parts = @()
            if ($null -ne $statusCode -and [string]$statusCode) {
                $parts += [string]$statusCode
            }
            if ($null -ne $reasonPhrase -and [string]$reasonPhrase) {
                $parts += [string]$reasonPhrase
            }
            if ($parts.Count -gt 0) {
                return ($parts -join " ")
            }
        }
    }

    return $exception.Message
}

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("GET", "POST")][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [hashtable]$Headers,
        [object]$Body
    )

    $requestParams = @{
        Method = $Method
        Uri = (Get-ApiUrl -Path $Path)
    }

    if ($Headers) {
        $requestParams.Headers = $Headers
    }

    if ($PSBoundParameters.ContainsKey("Body")) {
        $requestParams.Body = ($Body | ConvertTo-Json -Depth 8)
        $requestParams.ContentType = "application/json"
    }

    try {
        return Invoke-RestMethod @requestParams
    } catch {
        $detail = Get-HttpErrorDetail -ErrorRecord $_
        throw ("{0} {1} failed: {2}" -f $Method, $requestParams.Uri, $detail)
    }
}

function New-AuthHeaders {
    param(
        [Parameter(Mandatory = $true)][string]$LoginEmail,
        [Parameter(Mandatory = $true)][string]$LoginPassword
    )

    $loginResponse = Invoke-JsonRequest `
        -Method "POST" `
        -Path "/api/auth/login" `
        -Body @{
            email = $LoginEmail
            password = $LoginPassword
        }

    if (-not $loginResponse.access_token) {
        throw "Login succeeded but no access_token was returned."
    }

    return @{
        Authorization = "Bearer $($loginResponse.access_token)"
    }
}

function Get-TenderTargets {
    param([Parameter(Mandatory = $true)][hashtable]$Headers)

    if ($TenderIds -and $TenderIds.Count -gt 0) {
        $seen = [System.Collections.Generic.HashSet[int]]::new()
        $targets = [System.Collections.Generic.List[object]]::new()
        foreach ($tenderId in $TenderIds) {
            if ($seen.Add([int]$tenderId)) {
                $targets.Add([pscustomobject]@{
                    id = [int]$tenderId
                    title = $null
                    status = $null
                })
            }
        }

        return @($targets)
    }

    $targets = [System.Collections.Generic.List[object]]::new()
    $skip = 0

    while ($true) {
        $page = Invoke-JsonRequest `
            -Method "GET" `
            -Path ("/api/tenders?skip={0}&limit={1}" -f $skip, $PageSize) `
            -Headers $Headers

        $items = @($page.items)
        if ($items.Count -eq 0) {
            break
        }

        foreach ($item in $items) {
            $targets.Add([pscustomobject]@{
                id = [int]$item.id
                title = [string]$item.title
                status = [string]$item.status
            })

            if ($MaxTenders -gt 0 -and $targets.Count -ge $MaxTenders) {
                return @($targets)
            }
        }

        $skip += $items.Count
        if ($skip -ge [int]$page.total) {
            break
        }
    }

    return @($targets)
}

function Split-IntoBatches {
    param(
        [Parameter(Mandatory = $true)][object[]]$Items,
        [Parameter(Mandatory = $true)][int]$Size
    )

    $batches = [System.Collections.Generic.List[object[]]]::new()
    for ($index = 0; $index -lt $Items.Count; $index += $Size) {
        $take = [Math]::Min($Size, $Items.Count - $index)
        $slice = $Items[$index..($index + $take - 1)]
        $batches.Add(@($slice))
    }

    return @($batches)
}

function New-ResultRecord {
    param(
        [Parameter(Mandatory = $true)][int]$TenderId,
        [string]$Title,
        [string]$Status,
        [string]$JobStatus,
        [string]$ErrorMessage,
        [int]$JobId
    )

    return [pscustomobject]@{
        tender_id = $TenderId
        title = $Title
        tender_status = $Status
        job_id = $JobId
        job_status = $JobStatus
        error_message = $ErrorMessage
    }
}

function Request-BackfillBatch {
    param(
        [Parameter(Mandatory = $true)][object[]]$Batch,
        [Parameter(Mandatory = $true)][hashtable]$Headers
    )

    $requested = [System.Collections.Generic.List[object]]::new()

    foreach ($target in $Batch) {
        try {
            $response = Invoke-JsonRequest `
                -Method "POST" `
                -Path ("/api/admin/kpi/tenders/{0}/history/backfill" -f $target.id) `
                -Headers $Headers

            $requested.Add([pscustomobject]@{
                tender_id = [int]$target.id
                title = $target.title
                tender_status = $target.status
                job_id = [int]($response.job_id | ForEach-Object { $_ })
                last_seen_status = [string]$response.job_status
                requested_at = Get-Date
                timeout_at = (Get-Date).AddSeconds($JobTimeoutSeconds)
            })

            Write-Host ("[{0}] backfill richiesto, job #{1}, stato iniziale {2}" -f $target.id, $response.job_id, $response.job_status) -ForegroundColor Yellow
        } catch {
            $message = $_.Exception.Message
            Write-Host ("[{0}] richiesta backfill fallita: {1}" -f $target.id, $message) -ForegroundColor Red
            $script:Results.Add((New-ResultRecord -TenderId $target.id -Title $target.title -Status $target.status -JobStatus "failed" -ErrorMessage $message -JobId 0))
            if (-not $ContinueOnError) {
                throw
            }
        }
    }

    return @($requested)
}

function Wait-ForBatch {
    param(
        [Parameter(Mandatory = $true)][object[]]$Requested,
        [Parameter(Mandatory = $true)][hashtable]$Headers
    )

    $pending = @{}
    foreach ($item in $Requested) {
        $pending[[string]$item.tender_id] = $item
    }

    while ($pending.Count -gt 0) {
        foreach ($key in @($pending.Keys)) {
            $item = $pending[$key]

            if ((Get-Date) -gt $item.timeout_at) {
                $message = "Timeout after $JobTimeoutSeconds seconds."
                Write-Host ("[{0}] {1}" -f $item.tender_id, $message) -ForegroundColor Red
                $script:Results.Add((New-ResultRecord -TenderId $item.tender_id -Title $item.title -Status $item.tender_status -JobStatus "failed" -ErrorMessage $message -JobId $item.job_id))
                $pending.Remove($key)
                if (-not $ContinueOnError) {
                    throw $message
                }
                continue
            }

            try {
                $latest = Invoke-JsonRequest `
                    -Method "GET" `
                    -Path ("/api/admin/kpi/tenders/{0}/analysis-jobs/latest" -f $item.tender_id) `
                    -Headers $Headers

                $jobStatus = [string]$latest.job_status
                if (-not $jobStatus) {
                    $jobStatus = "not_requested"
                }

                if ($jobStatus -ne $item.last_seen_status) {
                    Write-Host ("[{0}] job #{1}: {2}" -f $item.tender_id, $item.job_id, $jobStatus) -ForegroundColor DarkGray
                    $item.last_seen_status = $jobStatus
                }

                switch ($jobStatus) {
                    "succeeded" {
                        Write-Host ("[{0}] backfill completato" -f $item.tender_id) -ForegroundColor Green
                        $script:Results.Add((New-ResultRecord -TenderId $item.tender_id -Title $item.title -Status $item.tender_status -JobStatus $jobStatus -ErrorMessage $null -JobId $item.job_id))
                        $pending.Remove($key)
                    }
                    "failed" {
                        $errorMessage = [string]$latest.error_message
                        if (-not $errorMessage) {
                            $errorMessage = "Analysis job failed."
                        }

                        Write-Host ("[{0}] job fallito: {1}" -f $item.tender_id, $errorMessage) -ForegroundColor Red
                        $script:Results.Add((New-ResultRecord -TenderId $item.tender_id -Title $item.title -Status $item.tender_status -JobStatus $jobStatus -ErrorMessage $errorMessage -JobId $item.job_id))
                        $pending.Remove($key)
                        if (-not $ContinueOnError) {
                            throw $errorMessage
                        }
                    }
                    default {
                    }
                }
            } catch {
                $message = $_.Exception.Message
                Write-Host ("[{0}] polling fallito: {1}" -f $item.tender_id, $message) -ForegroundColor Red
                $script:Results.Add((New-ResultRecord -TenderId $item.tender_id -Title $item.title -Status $item.tender_status -JobStatus "failed" -ErrorMessage $message -JobId $item.job_id))
                $pending.Remove($key)
                if (-not $ContinueOnError) {
                    throw
                }
            }
        }

        if ($pending.Count -gt 0) {
            Start-Sleep -Seconds $PollSeconds
        }
    }
}

$script:NormalizedBaseUrl = Normalize-BaseUrl -Url $BaseUrl
$script:Results = [System.Collections.Generic.List[object]]::new()

try {
    Write-Section -Message "Autenticazione"
    $resolvedPassword = Resolve-Password
    $headers = New-AuthHeaders -LoginEmail $Email -LoginPassword $resolvedPassword
    Write-Host ("Login riuscito per {0}" -f $Email) -ForegroundColor Green

    if (-not $SkipPortfolioResync) {
        Write-Section -Message "Portfolio Resync"
        $resyncResponse = Invoke-JsonRequest `
            -Method "POST" `
            -Path "/api/admin/kpi/portfolio/resync" `
            -Headers $headers

        $submitted = $resyncResponse.PSObject.Properties["submitted_tenders"]
        if ($null -ne $submitted) {
            Write-Host ("Resync portfolio richiesto per {0} tender" -f $submitted.Value) -ForegroundColor Green
        } else {
            Write-Host "Resync portfolio richiesto" -ForegroundColor Green
        }
    } else {
        Write-Host "Portfolio resync saltato" -ForegroundColor DarkYellow
    }

    Write-Section -Message "Discovery Tender"
    $targets = @(Get-TenderTargets -Headers $headers)
    if ($targets.Count -eq 0) {
        Write-Warning "Nessun tender trovato da processare."
        return
    }

    Write-Host ("Tender selezionati: {0}" -f $targets.Count) -ForegroundColor Green

    $batches = @(Split-IntoBatches -Items $targets -Size $BatchSize)
    Write-Host ("Batch previsti: {0}" -f $batches.Count) -ForegroundColor Green

    $batchNumber = 0
    foreach ($batch in $batches) {
        $batchNumber += 1
        Write-Section -Message ("Batch {0}/{1}" -f $batchNumber, $batches.Count)

        $requested = @(Request-BackfillBatch -Batch $batch -Headers $headers)
        if ($requested.Count -eq 0) {
            if (-not $ContinueOnError) {
                throw "No backfill requests were submitted in batch $batchNumber."
            }
            continue
        }

        Wait-ForBatch -Requested $requested -Headers $headers
    }
} finally {
    Write-Section -Message "Riepilogo"
    $successes = @($script:Results | Where-Object { $_.job_status -eq "succeeded" })
    $failures = @($script:Results | Where-Object { $_.job_status -ne "succeeded" })

    Write-Host ("Completati: {0}" -f $successes.Count) -ForegroundColor Green
    Write-Host ("Falliti: {0}" -f $failures.Count) -ForegroundColor Red

    if ($failures.Count -gt 0) {
        Write-Host ""
        Write-Host "Tender falliti:" -ForegroundColor Red
        foreach ($failure in $failures) {
            Write-Host ("- #{0} [{1}] {2}" -f $failure.tender_id, $failure.job_status, $failure.error_message)
        }
    }
}

$failedResults = @($script:Results | Where-Object { $_.job_status -ne "succeeded" })
if ($failedResults.Count -gt 0) {
    exit 1
}

exit 0
