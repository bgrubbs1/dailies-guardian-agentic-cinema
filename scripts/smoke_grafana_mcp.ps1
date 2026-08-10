[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = 'python'
}

$LokiImage = 'grafana/loki:3.5.1@sha256:a74594532eec4cc313401beedc4dd2708c43674c032084b1aeb87c14a5be1745'
$GrafanaImage = 'grafana/grafana:12.1.0@sha256:6ac590e7cabc2fbe8d7b8fc1ce9c9f0582177b334e0df9c927ebd9670469440f'
$McpImage = 'dailies-guardian:fixture-ui-20260809'
$ExpectedMcpImageId = 'sha256:298ce202151d779daea3e856f6d308e4e8fe0eb794dc391c3fa2ede685ac90f4'
if ((docker image inspect $McpImage --format '{{.Id}}') -ne $ExpectedMcpImageId) {
    throw 'The source-pinned local MCP image does not match the reviewed image ID.'
}

$Suffix = [guid]::NewGuid().ToString('N').Substring(0, 8)
$NetworkName = "dailies-grafana-smoke-$Suffix"
$LokiName = "dailies-loki-$Suffix"
$GrafanaName = "dailies-grafana-$Suffix"
$EvidenceDir = Join-Path ([IO.Path]::GetTempPath()) $NetworkName
New-Item -ItemType Directory -Path $EvidenceDir | Out-Null
$Anchor = (Get-Date).ToUniversalTime().AddHours(-2).ToString('yyyy-MM-ddTHH:mm:00Z')
& $Python (Join-Path $PSScriptRoot 'export_fixture.py') --anchor $Anchor --output $EvidenceDir |
    Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Synthetic fixture export failed.'
}

$LokiPortListener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$GrafanaPortListener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$LokiPortListener.Start()
$GrafanaPortListener.Start()
$LokiPort = ([Net.IPEndPoint]$LokiPortListener.LocalEndpoint).Port
$GrafanaPort = ([Net.IPEndPoint]$GrafanaPortListener.LocalEndpoint).Port
$LokiPortListener.Stop()
$GrafanaPortListener.Stop()

$AdminPassword = 'local-' + [guid]::NewGuid().ToString('N')
$NetworkCreated = $false
$LokiStarted = $false
$GrafanaStarted = $false

function Wait-LocalEndpoint {
    param([string]$Uri, [int]$ExpectedStatus = 200)
    for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
        try {
            $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 1
            if ($Response.StatusCode -eq $ExpectedStatus) {
                return
            }
        }
        catch {
            # Both services return transient startup errors before becoming ready.
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Timed out waiting for disposable endpoint: $Uri"
}

try {
    docker network create $NetworkName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Docker network creation failed.' }
    $NetworkCreated = $true

    docker run --rm -d --name $LokiName `
        --network $NetworkName --network-alias loki `
        -p "127.0.0.1:${LokiPort}:3100" `
        $LokiImage | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Loki failed to start.' }
    $LokiStarted = $true

    $Provisioning = Join-Path $ProjectRoot 'integration\grafana\provisioning'
    $Dashboards = Join-Path $ProjectRoot 'integration\grafana\dashboards'
    docker run --rm -d --name $GrafanaName `
        --network $NetworkName --network-alias grafana `
        -p "127.0.0.1:${GrafanaPort}:3000" `
        -e "GF_SECURITY_ADMIN_USER=admin" `
        -e "GF_SECURITY_ADMIN_PASSWORD=$AdminPassword" `
        -e 'GF_AUTH_ANONYMOUS_ENABLED=false' `
        -e 'GF_USERS_ALLOW_SIGN_UP=false' `
        --mount "type=bind,source=$Provisioning,target=/etc/grafana/provisioning,readonly" `
        --mount "type=bind,source=$Dashboards,target=/var/lib/grafana/dashboards,readonly" `
        $GrafanaImage | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Disposable Grafana failed to start.' }
    $GrafanaStarted = $true

    $LokiBase = "http://127.0.0.1:$LokiPort"
    $GrafanaBase = "http://127.0.0.1:$GrafanaPort"
    Wait-LocalEndpoint "$LokiBase/ready"
    Wait-LocalEndpoint "$GrafanaBase/api/health"

    $Push = Invoke-WebRequest -UseBasicParsing -Method Post `
        -Uri "$LokiBase/loki/api/v1/push" `
        -ContentType 'application/json' `
        -InFile (Join-Path $EvidenceDir 'loki_push_v1.json') `
        -TimeoutSec 10
    if ($Push.StatusCode -ne 204) { throw 'Disposable Loki rejected the fixture.' }

    $BasicValue = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes("admin:$AdminPassword")
    )
    $AdminHeaders = @{ Authorization = "Basic $BasicValue" }
    $Datasource = Invoke-RestMethod -Headers $AdminHeaders `
        -Uri "$GrafanaBase/api/datasources/uid/synthetic-loki" -TimeoutSec 10
    $Dashboard = Invoke-RestMethod -Headers $AdminHeaders `
        -Uri "$GrafanaBase/api/dashboards/uid/dailies-overview" -TimeoutSec 10
    if ($Datasource.uid -ne 'synthetic-loki' -or $Dashboard.dashboard.uid -ne 'dailies-overview') {
        throw 'Grafana did not provision the synthetic datasource and dashboard.'
    }

    $ServiceAccountBody = @{ name = "dailies-mcp-smoke-$Suffix"; role = 'Viewer' } |
        ConvertTo-Json
    $ServiceAccount = Invoke-RestMethod -Method Post -Headers $AdminHeaders `
        -Uri "$GrafanaBase/api/serviceaccounts" `
        -ContentType 'application/json' `
        -Body $ServiceAccountBody `
        -TimeoutSec 10
    $TokenBody = @{ name = "ephemeral-$Suffix" } | ConvertTo-Json
    $ServiceToken = Invoke-RestMethod -Method Post -Headers $AdminHeaders `
        -Uri "$GrafanaBase/api/serviceaccounts/$($ServiceAccount.id)/tokens" `
        -ContentType 'application/json' `
        -Body $TokenBody `
        -TimeoutSec 10

    $Start = $Anchor
    $End = ([datetime]::Parse($Anchor).ToUniversalTime().AddHours(2)).ToString('yyyy-MM-ddTHH:mm:ssZ')
    $McpOutput = docker run --rm `
        --network $NetworkName `
        -e 'GRAFANA_URL=http://grafana:3000' `
        -e "GRAFANA_SERVICE_ACCOUNT_TOKEN=$($ServiceToken.key)" `
        -e "SMOKE_START_RFC3339=$Start" `
        -e "SMOKE_END_RFC3339=$End" `
        -v "${PSScriptRoot}:/workspace/scripts:ro" `
        --entrypoint python `
        $McpImage /workspace/scripts/smoke_grafana_mcp.py
    if ($LASTEXITCODE -ne 0) { throw 'Official Grafana MCP smoke client failed.' }

    $McpResult = ($McpOutput -join "`n") | ConvertFrom-Json
    if ($McpResult.status -ne 'pass' -or $McpResult.tools_called.Count -ne 4) {
        throw 'Official Grafana MCP smoke result was incomplete.'
    }
    $Summary = [ordered]@{
        status = 'pass'
        grafana_image = $GrafanaImage
        loki_image = $LokiImage
        mcp_image_id = $ExpectedMcpImageId
        transport = $McpResult.transport
        write_mode = $McpResult.write_mode
        tools_called = $McpResult.tools_called
        datasource_uid = $McpResult.datasource_uid
        dashboard_uid = $McpResult.dashboard_uid
        production_ids_observed = $McpResult.production_ids_observed
        window = $McpResult.window
        loki_push_status = $Push.StatusCode
        service_account_role = 'Viewer'
        credential_persistence = 'none; disposable Grafana container only'
        evidence_directory = $EvidenceDir
    }
    $SummaryJson = $Summary | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText(
        (Join-Path $EvidenceDir 'grafana_mcp_smoke_result.json'),
        $SummaryJson + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    $SummaryJson
}
finally {
    if ($GrafanaStarted) { docker stop $GrafanaName | Out-Null }
    if ($LokiStarted) { docker stop $LokiName | Out-Null }
    if ($NetworkCreated) { docker network rm $NetworkName | Out-Null }
}
