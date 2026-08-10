[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = 'python'
}

$Image = 'grafana/loki:3.5.1@sha256:a74594532eec4cc313401beedc4dd2708c43674c032084b1aeb87c14a5be1745'
$ContainerName = 'dailies-loki-smoke-' + ([guid]::NewGuid().ToString('N').Substring(0, 8))
$EvidenceDir = Join-Path ([IO.Path]::GetTempPath()) $ContainerName
New-Item -ItemType Directory -Path $EvidenceDir | Out-Null

# The final fixture event is 1h45m after case-one start. Anchoring two hours
# back keeps every log in the past while remaining inside Loki's default
# recent-ingestion window.
$Anchor = (Get-Date).ToUniversalTime().AddHours(-2).ToString('yyyy-MM-ddTHH:mm:00Z')
& $Python (Join-Path $PSScriptRoot 'export_fixture.py') `
    --anchor $Anchor `
    --output $EvidenceDir | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Synthetic fixture export failed.'
}

$Listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$Listener.Start()
$Port = ([Net.IPEndPoint]$Listener.LocalEndpoint).Port
$Listener.Stop()
$ContainerStarted = $false

try {
    $ContainerId = docker run --rm -d --name $ContainerName `
        -p "127.0.0.1:${Port}:3100" $Image
    if ($LASTEXITCODE -ne 0) {
        throw 'Disposable Loki failed to start.'
    }
    $ContainerStarted = $true
    $BaseUrl = "http://127.0.0.1:$Port"

    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
        try {
            $Probe = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/ready" -TimeoutSec 1
            if ($Probe.StatusCode -eq 200) {
                $Ready = $true
                break
            }
        }
        catch {
            # Startup returns 503 until the single-node rings are active.
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $Ready) {
        docker logs $ContainerName --tail 50 | Out-Host
        throw 'Disposable Loki did not become ready.'
    }

    $PayloadPath = Join-Path $EvidenceDir 'loki_push_v1.json'
    $Push = Invoke-WebRequest -UseBasicParsing -Method Post `
        -Uri "$BaseUrl/loki/api/v1/push" `
        -ContentType 'application/json' `
        -InFile $PayloadPath `
        -TimeoutSec 10

    $Payload = Get-Content -LiteralPath $PayloadPath -Raw | ConvertFrom-Json
    $AllTimes = @(
        $Payload.streams |
            ForEach-Object { $_.values | ForEach-Object { [Int64]$_[0] } } |
            Sort-Object
    )
    $Start = ([Int64]$AllTimes[0] - [Int64]60000000000).ToString()
    $End = ([Int64]$AllTimes[-1] + [Int64]60000000000).ToString()
    $Query = [uri]::EscapeDataString('{environment="synthetic"}')
    $QueryUri = "$BaseUrl/loki/api/v1/query_range?query=$Query&start=$Start&end=$End&limit=100&direction=forward"
    $Result = Invoke-RestMethod -Uri $QueryUri -TimeoutSec 10
    $ReturnedLogs = @($Result.data.result | ForEach-Object { $_.values }).Count

    if (
        $Push.StatusCode -ne 204 -or
        $Result.status -ne 'success' -or
        @($Result.data.result).Count -ne 3 -or
        $ReturnedLogs -ne $AllTimes.Count
    ) {
        throw 'Loki did not return all seven logs across the three synthetic streams.'
    }

    [ordered]@{
        status = 'pass'
        image = $Image
        container_id = $ContainerId
        anchor_utc = $Anchor
        ready_status = 200
        push_status = $Push.StatusCode
        result_type = $Result.data.resultType
        streams = @($Result.data.result).Count
        logs = $ReturnedLogs
        expected_logs = $AllTimes.Count
        evidence_directory = $EvidenceDir
    } | ConvertTo-Json
}
finally {
    if ($ContainerStarted) {
        docker stop $ContainerName | Out-Null
    }
}
