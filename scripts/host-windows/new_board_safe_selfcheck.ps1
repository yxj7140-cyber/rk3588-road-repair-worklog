param(
    [Parameter(Mandatory = $true)]
    [string]$BoardIp,

    [string]$User = "rock",

    [string]$KeyPath = "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519",

    [string]$ExpectedHyperBootMd5 = "44ac4e9524aa40bccfc602f21c1c35a7",

    [int]$WebPort = 8080
)

$ErrorActionPreference = "Stop"

function Add-Result {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail = ""
    )
    [pscustomobject]@{
        Check = $Name
        Status = $Status
        Detail = $Detail
    }
}

function Invoke-BoardSsh {
    param([string]$Command)

    $sshArgs = @(
        "-i", $KeyPath,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=no",
        "$User@$BoardIp",
        $Command
    )

    & ssh @sshArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "ssh failed with exit code $LASTEXITCODE"
    }
}

$results = New-Object System.Collections.Generic.List[object]

try {
    $pingOk = Test-Connection -ComputerName $BoardIp -Count 1 -Quiet
    if ($pingOk) {
        $results.Add((Add-Result "Ping" "PASS" $BoardIp))
    } else {
        $results.Add((Add-Result "Ping" "WARN" "ICMP failed; SSH may still work"))
    }
} catch {
    $results.Add((Add-Result "Ping" "WARN" $_.Exception.Message))
}

try {
    $who = Invoke-BoardSsh "hostname; id -un; ip -br addr; ip route"
    $results.Add((Add-Result "SSH" "PASS" (($who -join " ") -replace "\s+", " ")))
} catch {
    $results.Add((Add-Result "SSH" "FAIL" $_.Exception.Message))
    $results | Format-Table -AutoSize
    exit 2
}

try {
    $md5Line = (Invoke-BoardSsh "md5sum /boot/HyperBoot.bin | awk '{print `$1}'" | Select-Object -First 1).Trim()
    if ($md5Line -eq $ExpectedHyperBootMd5) {
        $results.Add((Add-Result "HyperBoot MD5" "PASS" $md5Line))
    } else {
        $results.Add((Add-Result "HyperBoot MD5" "FAIL" "actual=$md5Line expected=$ExpectedHyperBootMd5"))
    }
} catch {
    $results.Add((Add-Result "HyperBoot MD5" "FAIL" $_.Exception.Message))
}

try {
    $dirs = Invoke-BoardSsh "test -d /home/rock/road_repair_web_remote && echo web_remote=ok; test -d /home/rock/road_repair_chassis_migration && echo chassis_migration=ok"
    $dirsText = $dirs -join " "
    if ($dirsText -match "web_remote=ok" -and $dirsText -match "chassis_migration=ok") {
        $results.Add((Add-Result "Required dirs" "PASS" $dirsText))
    } else {
        $results.Add((Add-Result "Required dirs" "FAIL" $dirsText))
    }
} catch {
    $results.Add((Add-Result "Required dirs" "FAIL" $_.Exception.Message))
}

try {
    $svc = Invoke-BoardSsh "systemctl is-enabled road-repair-web-remote.service; systemctl is-active road-repair-web-remote.service"
    $svcText = ($svc -join " ").Trim()
    if ($svcText -match "enabled" -and $svcText -match "active") {
        $results.Add((Add-Result "Web service" "PASS" $svcText))
    } else {
        $results.Add((Add-Result "Web service" "FAIL" $svcText))
    }
} catch {
    $results.Add((Add-Result "Web service" "FAIL" $_.Exception.Message))
}

try {
    $statusUrl = "http://${BoardIp}:$WebPort/api/status"
    $api = Invoke-RestMethod -Uri $statusUrl -TimeoutSec 5
    $apiJson = $api | ConvertTo-Json -Compress -Depth 8
    $safePattern = "safe|lock|false|disabled"
    if ($apiJson -match $safePattern) {
        $results.Add((Add-Result "Web API / safe-lock" "PASS" $apiJson))
    } else {
        $results.Add((Add-Result "Web API / safe-lock" "WARN" "Review manually: $apiJson"))
    }
} catch {
    $results.Add((Add-Result "Web API / safe-lock" "FAIL" $_.Exception.Message))
}

try {
    $can = Invoke-BoardSsh "ip -br link; ip -details link show can0 2>/dev/null || true"
    $canText = ($can -join " ") -replace "\s+", " "
    if ($canText -match "can0") {
        $results.Add((Add-Result "CAN visible" "PASS" $canText))
    } else {
        $results.Add((Add-Result "CAN visible" "WARN" "can0 not visible in output"))
    }
} catch {
    $results.Add((Add-Result "CAN visible" "WARN" $_.Exception.Message))
}

try {
    $selfcheck = Invoke-BoardSsh "if [ -d /home/rock/road_repair_chassis_migration ]; then cd /home/rock/road_repair_chassis_migration && if [ -x ./run_road_repair_migration_selfcheck.sh ]; then ./run_road_repair_migration_selfcheck.sh; elif [ -f ./run_road_repair_migration_selfcheck.sh ]; then bash ./run_road_repair_migration_selfcheck.sh; else echo selfcheck_script_missing; fi; else echo chassis_dir_missing; fi"
    $selfcheckText = ($selfcheck -join " ") -replace "\s+", " "
    if ($selfcheckText -match "missing") {
        $results.Add((Add-Result "Migration selfcheck" "WARN" $selfcheckText))
    } else {
        $results.Add((Add-Result "Migration selfcheck" "PASS" $selfcheckText))
    }
} catch {
    $results.Add((Add-Result "Migration selfcheck" "WARN" $_.Exception.Message))
}

$results.Add((Add-Result "Motion allowed" "NO" "This script never unlocks current or sends movement commands."))

$results | Format-Table -AutoSize

if ($results.Status -contains "FAIL") {
    exit 1
}

exit 0
