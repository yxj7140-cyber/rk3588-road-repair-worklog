param(
    [string]$BoardSsid = "rockchip_decdfa",
    [string]$RestoreSsid = "HUST_WIRELESS",
    [string]$HostName = "192.168.1.1",
    [string]$User = "rock",
    [string]$IdentityFile = "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519",
    [switch]$UseStaticIPv4,
    [string]$StaticIPv4 = "192.168.1.2",
    [int]$StaticPrefixLength = 24,
    [string]$RemoteCommand = "",
    [string]$RemoteCommandFile = "",
    [switch]$DeployBoardPiper
)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir ("wifi_probe_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

function Log-Line {
    param([string]$Text)
    $line = "$(Get-Date -Format 'HH:mm:ss') $Text"
    Write-Host $line
    Add-Content -LiteralPath $LogPath -Value $line
}

function Wait-WlanSsid {
    param(
        [string]$Ssid,
        [int]$TimeoutSec = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $info = netsh wlan show interfaces
        $ssidLine = $info | Where-Object { $_ -match '^\s*SSID\s*:' -and $_ -notmatch 'BSSID' } | Select-Object -First 1
        if ($ssidLine -and ($ssidLine -replace '^\s*SSID\s*:\s*', '') -eq $Ssid) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

try {
    Log-Line "Log: $LogPath"
    Log-Line "Disconnecting WLAN before hotspot switch"
    netsh wlan disconnect interface="WLAN" | Tee-Object -FilePath $LogPath -Append
    Start-Sleep -Seconds 2
    Log-Line "Connecting WLAN to board SSID: $BoardSsid"
    netsh wlan connect name="$BoardSsid" ssid="$BoardSsid" interface="WLAN" | Tee-Object -FilePath $LogPath -Append

    if (-not (Wait-WlanSsid -Ssid $BoardSsid -TimeoutSec 35)) {
        Log-Line "Failed to connect to $BoardSsid within timeout."
        exit 2
    }

    Log-Line "Connected to $BoardSsid"

    if ($UseStaticIPv4) {
        Log-Line "Applying temporary static IPv4 on WLAN: $StaticIPv4/$StaticPrefixLength"
        netsh interface ipv4 set address name="WLAN" static $StaticIPv4 255.255.255.0 | Tee-Object -FilePath $LogPath -Append
        Start-Sleep -Seconds 2
    }

    ipconfig | Tee-Object -FilePath $LogPath -Append

    Log-Line "Ping board: $HostName"
    ping -n 3 $HostName | Tee-Object -FilePath $LogPath -Append
    if ($LASTEXITCODE -ne 0) {
        Log-Line "Ping failed."
        exit 3
    }

    $remote = "${User}@${HostName}"
    Log-Line "SSH probe: $remote"
    ssh -i $IdentityFile -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no $remote "echo BOARD_OK && hostname && ip -4 addr show" 2>&1 |
        Tee-Object -FilePath $LogPath -Append
    if ($LASTEXITCODE -ne 0) {
        Log-Line "SSH failed."
        exit 4
    }

    if ($DeployBoardPiper) {
        Log-Line "Deploying board_piper files."
        powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "deploy_board_piper_to_board.ps1") -HostName $HostName -User $User -IdentityFile $IdentityFile 2>&1 |
            Tee-Object -FilePath $LogPath -Append
        if ($LASTEXITCODE -ne 0) {
            Log-Line "Deploy failed."
            exit 5
        }
    }

    if ($RemoteCommandFile) {
        if (-not (Test-Path -LiteralPath $RemoteCommandFile)) {
            throw "Remote command file not found: $RemoteCommandFile"
        }
        Log-Line "Running remote command file: $RemoteCommandFile"
        ((Get-Content -Raw -LiteralPath $RemoteCommandFile) -replace "`r`n", "`n" -replace "`r", "`n") |
            ssh -i $IdentityFile -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no $remote "bash -s" 2>&1 |
            Tee-Object -FilePath $LogPath -Append
        if ($LASTEXITCODE -ne 0) {
            Log-Line "Remote command file failed."
            exit 6
        }
    }
    elseif ($RemoteCommand) {
        Log-Line "Running remote command: $RemoteCommand"
        ssh -i $IdentityFile -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no $remote $RemoteCommand 2>&1 |
            Tee-Object -FilePath $LogPath -Append
        if ($LASTEXITCODE -ne 0) {
            Log-Line "Remote command failed."
            exit 6
        }
    }

    Log-Line "Board Wi-Fi probe OK."
} finally {
    if ($UseStaticIPv4) {
        Log-Line "Restoring WLAN IPv4 DHCP"
        netsh interface ipv4 set address name="WLAN" dhcp | Tee-Object -FilePath $LogPath -Append
        netsh interface ipv4 set dnsservers name="WLAN" dhcp | Tee-Object -FilePath $LogPath -Append
    }
    Log-Line "Restoring WLAN to: $RestoreSsid"
    netsh wlan connect name="$RestoreSsid" ssid="$RestoreSsid" interface="WLAN" | Tee-Object -FilePath $LogPath -Append
    Start-Sleep -Seconds 5
    netsh wlan show interfaces | Tee-Object -FilePath $LogPath -Append
    Log-Line "Finished. Log saved at $LogPath"
}
